# models/cluster_scheduler.py

import asyncio
from typing import Dict, FrozenSet, Set, Tuple

from config.base import settings
from models.cluster_manager import ClusterManager
from models.cluster_executor import ClusterExecutor
from messages.simulation.simulation_clusters import SimulationClustersMessage
from messages.simulation import SimulationTickMessage
import logging

_logger = logging.getLogger(__name__)


class ClusterScheduler:
    def __init__(self, world, executor: ClusterExecutor = None):
        self.world = world
        self.db = world._db
        self.simulation_id = world.simulation_id

        self.cluster_manager = ClusterManager(world)
        self.executor = executor or ClusterExecutor(self.db, world._nats, world._milvus)

        # cluster → (task, unblock event)
        self._cluster_tasks: Dict[FrozenSet[str], Tuple[asyncio.Task, asyncio.Event]] = {}
        # cluster → last tick
        self._cluster_ticks: Dict[FrozenSet[str], int] = {}
        # whenever a cluster finishes a tick
        self._finished_queue: asyncio.Queue = asyncio.Queue()
        # controller + periodic sync handles
        self._controller_task: asyncio.Task | None = None
        self._periodic_task: asyncio.Task | None = None

    async def start(self):
        # 1) initial clusters
        raw = self.cluster_manager.compute_clusters()
        clusters = {frozenset(c) for c in raw}
        for c in clusters:
            self._cluster_ticks[c] = 0
            evt = asyncio.Event()
            evt.set()  # ready immediately
            task = asyncio.create_task(self._cluster_loop(c, evt))
            self._cluster_tasks[c] = (task, evt)

        # 2) start the event-driven controller
        self._controller_task = asyncio.create_task(self._controller_loop())
        # 3) start periodic re-clustering (every 0.1s)
        self._periodic_task = asyncio.create_task(self._periodic_recluster())

    async def stop(self):
        # nothing to do if we never ran
        if not self._cluster_ticks:
            return

        # cancel periodic
        if self._periodic_task:
            self._periodic_task.cancel()
            try: await self._periodic_task
            except asyncio.CancelledError: pass

        # figure out how far ahead the fastest cluster got
        max_tick = max(self._cluster_ticks.values())

        # cancel the controller
        if self._controller_task:
            self._controller_task.cancel()
            try: await self._controller_task
            except asyncio.CancelledError: pass

        # cancel all cluster loops
        for task, _ in self._cluster_tasks.values():
            task.cancel()
            try: await task
            except asyncio.CancelledError: pass

        # flush each lagging cluster inline
        for cluster, current in list(self._cluster_ticks.items()):
            delta = max_tick - current
            for i in range(delta):
                await self.executor.run(cluster, current + i)
            self._cluster_ticks[cluster] = max_tick

    async def _cluster_loop(self, cluster: FrozenSet[str], unblock: asyncio.Event):
        """Dedicated loop per cluster."""
        tick = 0
        try:
            while True:
                await unblock.wait()
                await self.executor.run(cluster, tick)
                tick += 1
                self._cluster_ticks[cluster] = tick
                unblock.clear()
                await self._finished_queue.put((cluster, tick))
        except asyncio.CancelledError:
            return

    async def _controller_loop(self):
        """Recompute on every finished‐tick event, save snapshots, and unblock."""
        current_global_tick = 0
        pending_clusters = set(self._cluster_tasks)  # all clusters must finish the next tick

        try:
            while True:
                # wait for the next cluster to finish
                finished_cluster, finished_tick = await self._finished_queue.get()

                # only care about the *next* tick barrier
                if finished_tick == current_global_tick + 1:
                    pending_clusters.discard(finished_cluster)

                # once every cluster has finished tick `current_global_tick+1`…
                if not pending_clusters:
                    # 1) advance global world tick exactly once (deprecated)
                    # NOTE: global world.tick is no longer used in cluster-optimized mode
                    # await self.world.tick()

                    # 2) broadcast the global‐tick event
                    msg = SimulationTickMessage(self.simulation_id, current_global_tick+1)
                    await self.world._nats.publish(
                        msg.model_dump_json(), msg.get_channel_name()
                    )

                    # 3) bump your global counter
                    current_global_tick += 1

                    # 4) reset your barrier for the *next* tick
                    pending_clusters = set(self._cluster_tasks)
                # 1) recompute clusters after every tick
                raw = self.cluster_manager.compute_clusters()
                new_clusters = {frozenset(c) for c in raw}

                # 2) record positions & edges for snapshot
                all_agents = self.cluster_manager._load_agents()
                positions = {a["id"]: (a["x"], a["y"]) for a in all_agents}

                edges = []
                for c1 in new_clusters:
                    t1 = self._cluster_ticks.get(c1, 0)
                    for c2 in new_clusters:
                        if c1 is c2: continue
                        t2 = self._cluster_ticks.get(c2, 0)
                        if t2 < t1:
                            for u in c1:
                                for v in c2:
                                    a = next(x for x in all_agents if x["id"] == u)
                                    b = next(x for x in all_agents if x["id"] == v)
                                    dist = abs(a["x"]-b["x"]) + abs(a["y"]-b["y"])
                                    thresh = a["vis_range"] + a["max_move"]
                                    if dist <= thresh:
                                        edges.append((u, v))
                                        break
                                else:
                                    continue
                                break

                # 3) save the snapshot
                table = self.db.table(settings.tinydb.tables.cluster_snapshot_table)
                table.insert({
                    "simulation_id": self.simulation_id,
                    "tick": finished_tick,
                    "nodes": [a["id"] for a in all_agents],
                    "positions": positions,
                    "edges": edges,
                })

                # 4) notify any subscribers
                msg = SimulationClustersMessage(
                    id=self.simulation_id,
                    tick=finished_tick,
                    clusters=[list(c) for c in raw],
                )
                await self.world._nats.publish(
                    subject=msg.get_channel_name(),
                    message=msg.model_dump_json(),
                )

                # 5) merge / split tasks
                self._sync_tasks_to_clusters(new_clusters)

                # 6) unblock any clusters that are no longer blocked
                for c, (_t, unblock) in self._cluster_tasks.items():
                    if not self._is_blocked(c):
                        unblock.set()

        except asyncio.CancelledError:
            return

    async def _periodic_recluster(self):
        """Every 0.1s, re-compute clusters so we catch splits ASAP."""
        try:
            while True:
                await asyncio.sleep(0.1)
                raw = self.cluster_manager.compute_clusters()
                new_clusters = {frozenset(c) for c in raw}
                # if anything changed, re-sync
                if new_clusters != set(self._cluster_tasks.keys()):
                    self._sync_tasks_to_clusters(new_clusters)
                    for c, (_t, unblock) in self._cluster_tasks.items():
                        if not self._is_blocked(c):
                            unblock.set()
        except asyncio.CancelledError:
            return

    def _sync_tasks_to_clusters(self, new_clusters: Set[FrozenSet[str]]):
        """Cancel old, spawn new clusters, inherit ticks on merge/split."""
        # cancel departed
        for old in list(self._cluster_tasks):
            if old not in new_clusters:
                task, _ = self._cluster_tasks.pop(old)
                task.cancel()
                self._cluster_ticks.pop(old, None)

        existing = set(self._cluster_ticks.keys())
        to_cancel = existing - new_clusters

        # spawn + inherit
        for new_c in new_clusters - existing:
            if any(old.issubset(new_c) for old in existing):
                sources = [self._cluster_ticks[old] for old in existing if old.issubset(new_c)]
            else:
                sources = [self._cluster_ticks[old] for old in existing if new_c.issubset(old)]
            inherited = max(sources, default=0)

            self._cluster_ticks[new_c] = inherited
            evt = asyncio.Event()
            evt.clear()
            task = asyncio.create_task(self._cluster_loop(new_c, evt))
            self._cluster_tasks[new_c] = (task, evt)

        # finally, cancel truly gone
        for old in to_cancel:
            task, _ = self._cluster_tasks.pop(old)
            task.cancel()
            self._cluster_ticks.pop(old, None)

    def _is_blocked(self, cluster: FrozenSet[str]) -> bool:
        """Return True if `cluster` must wait on a slower one in range."""
        my_tick = self._cluster_ticks.get(cluster, 0)
        agents = self.cluster_manager._load_agents()
        idx = {a["id"]: a for a in agents}
        for other, other_tick in self._cluster_ticks.items():
            if other is cluster or other_tick >= my_tick:
                continue
            for aid in cluster:
                for bid in other:
                    a = idx[aid]; b = idx[bid]
                    dist = abs(a["x"] - b["x"]) + abs(a["y"] - b["y"])
                    if dist <= (a["vis_range"] + a["max_move"]):
                        return True
        return False
