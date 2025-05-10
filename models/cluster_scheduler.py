# cluster_scheduler.py

import asyncio
from typing import Dict, FrozenSet, Set, Tuple, List

from models.cluster_manager import ClusterManager
from models.cluster_executor import ClusterExecutor
from messages.simulation.simulation_clusters import SimulationClustersMessage



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
        # Queue for cluster‐finished notifications
        self._finished_queue: asyncio.Queue = asyncio.Queue()
        # Controller task handle
        self._controller_task: asyncio.Task | None = None

    async def start(self):
        # 1) initial clusters
        raw = self.cluster_manager.compute_clusters()
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
        # 1) cancel controller; we manage catch-up ourselves
        if self._controller_task:
            self._controller_task.cancel()
            try:
                await self._controller_task
            except asyncio.CancelledError:
                pass

        # 2) determine the highest tick any cluster reached
        if not self._cluster_ticks:
            return
        max_tick = max(self._cluster_ticks.values())

        # 3) block clusters at max, unblock slower ones
        for c, (_task, unblock) in self._cluster_tasks.items():
            if self._cluster_ticks[c] >= max_tick:
                unblock.clear()
            else:
                unblock.set()

        # 4) wait for all clusters to catch up
        while True:
            # check if all clusters at max
            if all(tick >= max_tick for tick in self._cluster_ticks.values()):
                break
            # wait for any cluster to finish another tick
            try:
                finished_cluster, tick = await asyncio.wait_for(
                    self._finished_queue.get(),
                    timeout=5.0  # avoid hanging indefinitely
                )
            except asyncio.TimeoutError:
                raise RuntimeError("Timed out waiting for clusters to catch up on stop()")
            # update tick (cluster_loop already did, but ensure consistency)
            self._cluster_ticks[finished_cluster] = tick
            # re-block any that reached max
            if tick >= max_tick:
                _, ev = self._cluster_tasks[finished_cluster]
                ev.clear()
            else:
                # ensure slower clusters remain unblocked
                _, ev = self._cluster_tasks[finished_cluster]
                ev.set()

        # 5) now cancel all cluster tasks
        for task, _ in self._cluster_tasks.values():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

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
        """Recompute clusters on each cluster finish, merge/split, publish, and unblock."""
        try:
            while True:
                finished_cluster, finished_tick = await self._finished_queue.get()

                # 1) recompute clusters
                raw = self.cluster_manager.compute_clusters()
                new_clusters = {frozenset(c) for c in raw}

                # 2) publish updated clusters
                msg = SimulationClustersMessage(
                    id=self.simulation_id,
                    tick=finished_tick,
                    clusters=[list(c) for c in raw],
                )
                await self.world._nats.publish(
                    subject=msg.get_channel_name(),
                    message=msg.model_dump_json(),
                )

                # 3) sync tasks to new clusters (merge/split)
                self._sync_tasks_to_clusters(new_clusters)

                # 4) unblock any clusters not blocked by others
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

        # spawn new clusters
        for c in new_clusters:
            if c not in self._cluster_tasks:
                # inherit the max tick of any subset clusters
                inherited = max(
                    (self._cluster_ticks.get(old, 0) for old in self._cluster_ticks if old.issubset(c)),
                    default=0
                )
                self._cluster_ticks[c] = inherited
                evt = asyncio.Event()
                evt.clear()  # will be unblocked by controller if ready
                task = asyncio.create_task(self._cluster_loop(c, evt))
                self._cluster_tasks[c] = (task, evt)

    def _is_blocked(self, cluster: FrozenSet[str]) -> bool:
        """Return True if `cluster` must wait on a slower cluster in range."""
        my_tick = self._cluster_ticks.get(cluster, 0)
        agents = self.cluster_manager._load_agents()
        agent_map = {a["id"]: a for a in agents}
        for other, other_tick in self._cluster_ticks.items():
            if other is cluster or other_tick >= my_tick:
                continue
            # check any agent pairs across clusters
            for aid in cluster:
                for bid in other:
                    a = agent_map[aid]
                    b = agent_map[bid]
                    dist = abs(a["x"] - b["x"]) + abs(a["y"] - b["y"])
                    threshold = a["vis_range"] + a["max_move"]
                    if dist <= threshold:
                        return True
        return False
