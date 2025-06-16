# models/cluster_scheduler.py

import asyncio
from typing import Dict, FrozenSet, Set, Tuple, List

from config.base import settings
from models.cluster_manager import ClusterManager
from models.cluster_executor import ClusterExecutor
from messages.simulation.simulation_clusters import SimulationClustersMessage
import logging

_logger = logging.getLogger(__name__)


class ClusterScheduler:
    def __init__(self, world, executor: ClusterExecutor = None):
        self.world = world
        self.db = world._db
        self.simulation_id = world.simulation_id

        self.cluster_manager = ClusterManager(world)
        self.executor = executor or ClusterExecutor(self.db, world._nats, world._milvus)

        # Maps each cluster (frozenset of agent IDs) to (Task, unblock Event)
        self._cluster_tasks: Dict[FrozenSet[str], Tuple[asyncio.Task, asyncio.Event]] = {}
        # Last tick executed per cluster
        self._cluster_ticks: Dict[FrozenSet[str], int] = {}
        # Queue for cluster-finished notifications
        self._finished_queue: asyncio.Queue = asyncio.Queue()
        # Controller task handle
        self._controller_task: asyncio.Task | None = None

    async def start(self):
        # 1) initial clusters
        raw = self.cluster_manager.compute_clusters()
        init_msg = SimulationClustersMessage(
            id=self.simulation_id,
            tick=0,
            clusters=[list(c) for c in raw],
        )
        await self.world._nats.publish(
            subject=init_msg.get_channel_name(),
            message=init_msg.model_dump_json(),
        )
        clusters = {frozenset(c) for c in raw}
        for c in clusters:
            self._cluster_ticks[c] = 0
            evt = asyncio.Event()
            evt.set()  # ready to run
            task = asyncio.create_task(self._cluster_loop(c, evt))
            self._cluster_tasks[c] = (task, evt)

        # 2) start controller
        self._controller_task = asyncio.create_task(self._controller_loop())

    async def stop(self):
        # 1) If no clusters ran yet, nothing to do.
        if not self._cluster_ticks:
            return

        # 2) Figure out how far ahead the fastest cluster got.
        max_tick = max(self._cluster_ticks.values())

        # 3) Cancel the controller loop (if running) and all cluster tasks
        if self._controller_task:
            self._controller_task.cancel()
            try:
                await self._controller_task
            except asyncio.CancelledError:
                pass

        for task, _ in self._cluster_tasks.values():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # 4) Now “flush” each lagging cluster by running exactly
        #    (max_tick – current_tick) more ticks in-line:
        for cluster, current in list(self._cluster_ticks.items()):
            delta = max_tick - current
            for i in range(delta):
                # note: using the same executor you passed in
                await self.executor.run(cluster, current + i)
            # set it to the final tick
            self._cluster_ticks[cluster] = max_tick

        # Shutdown is complete.

    async def _cluster_loop(self, cluster: FrozenSet[str], unblock: asyncio.Event):
        """One dedicated task per cluster."""
        tick = 0
        try:
            while True:
                await unblock.wait()
                # advance one tick
                await self.executor.run(cluster, tick)
                tick += 1
                self._cluster_ticks[cluster] = tick

                # block until controller says otherwise
                unblock.clear()
                # notify controller / stop() catcher
                await self._finished_queue.put((cluster, tick))

        except asyncio.CancelledError:
            return

    async def _controller_loop(self):
        """Recompute clusters on each cluster finish, save snapshot, publish, and unblock."""
        try:
            while True:
                finished_cluster, finished_tick = await self._finished_queue.get()

                # 1) recompute clusters
                raw = self.cluster_manager.compute_clusters()
                new_clusters = {frozenset(c) for c in raw}

                # 2) load all agent positions for this snapshot
                all_agents = self.cluster_manager._load_agents()
                positions = {a["id"]: (a["x"], a["y"]) for a in all_agents}

                # 3) compute dependency edges between clusters
                edges = []
                for c1 in new_clusters:
                    t1 = self._cluster_ticks.get(c1, 0)
                    for c2 in new_clusters:
                        if c1 is c2:
                            continue
                        t2 = self._cluster_ticks.get(c2, 0)
                        if t2 < t1:
                            for u in c1:
                                for v in c2:
                                    a = next(filter(lambda x: x["id"] == u, all_agents))
                                    b = next(filter(lambda x: x["id"] == v, all_agents))
                                    dist = abs(a["x"] - b["x"]) + abs(a["y"] - b["y"])
                                    threshold = a["vis_range"] + a["max_move"]
                                    if dist <= threshold:
                                        edges.append((u, v))
                                        break
                                else:
                                    continue
                                break

                # 4) save snapshot into TinyDB
                table = self.db.table(settings.tinydb.tables.cluster_snapshot_table)
                table.insert({
                    "simulation_id": self.simulation_id,
                    "tick":          finished_tick,
                    "nodes":         [a["id"] for a in all_agents],
                    "positions":     positions,
                    "edges":         edges,
                })

                # 5) publish updated clusters
                msg = SimulationClustersMessage(
                    id=self.simulation_id,
                    tick=finished_tick,
                    clusters=[list(c) for c in raw],
                )
                await self.world._nats.publish(
                    subject=msg.get_channel_name(),
                    message=msg.model_dump_json(),
                )

                # 6) sync tasks to new clusters (merge/split)
                self._sync_tasks_to_clusters(new_clusters)

                # 7) unblock any clusters not blocked by others
                for c, (_t, unblock) in self._cluster_tasks.items():
                    if not self._is_blocked(c):
                        unblock.set()
        except asyncio.CancelledError:
            return

    def _sync_tasks_to_clusters(self, new_clusters: Set[FrozenSet[str]]):
        """Cancel tasks for departed clusters, spawn tasks for new clusters."""
        # cancel old clusters
        for old in list(self._cluster_tasks):
            if old not in new_clusters:
                task, _ = self._cluster_tasks.pop(old)
                task.cancel()
                self._cluster_ticks.pop(old, None)

        existing = set(self._cluster_ticks.keys())
        to_cancel = existing - new_clusters

        # spawn new clusters
        for new_c in new_clusters - existing:
            # merge if any old ⊆ new_c, else split if new_c ⊆ old
            if any(old.issubset(new_c) for old in existing):
                sources = [self._cluster_ticks[old] for old in existing if old.issubset(new_c)]
            else:
                sources = [self._cluster_ticks[old] for old in existing if new_c.issubset(old)]
            inherited = max(sources, default=0)

            self._cluster_ticks[new_c] = inherited
            evt = asyncio.Event()
            evt.clear()  # initially blocked until controller_step 7
            task = asyncio.create_task(self._cluster_loop(new_c, evt))
            self._cluster_tasks[new_c] = (task, evt)

        # finally cancel truly departed
        for old in to_cancel:
            task, _ = self._cluster_tasks.pop(old)
            task.cancel()
            self._cluster_ticks.pop(old, None)

    def _is_blocked(self, cluster: FrozenSet[str]) -> bool:
        """Return True if `cluster` must wait on a slower cluster in range."""
        my_tick = self._cluster_ticks.get(cluster, 0)
        agents = self.cluster_manager._load_agents()
        agent_map = {a["id"]: a for a in agents}
        for other, other_tick in self._cluster_ticks.items():
            # only consider clusters that are strictly behind in ticks
            if other is cluster or other_tick >= my_tick:
                continue
            lag = my_tick - other_tick
            for aid in cluster:
                for bid in other:
                    a = agent_map[aid]
                    b = agent_map[bid]
                    dist = abs(a["x"] - b["x"]) + abs(a["y"] - b["y"])
                    # dynamic threshold: agents could meet within lag ticks
                    threshold = a["vis_range"] + lag * a["max_move"]
                    if dist <= threshold:
                        return True
        return False
