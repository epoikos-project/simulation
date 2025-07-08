from loguru import logger

from engine.context.base import BaseContext


class PlanContext(BaseContext):

    def build(self) -> str:
        # ownership
        if self.agent.owned_plan:
            plan_ownership_context = "You are the owner of the following plan: "
            plan_ownership_context += str(self.agent.owned_plan) + " "
            if self.agent.owned_plan.tasks:
                plan_ownership_context += (
                    "These are the current tasks associated with this plan: "
                    + ", ".join(map(str, self.agent.owned_plan.tasks))
                )
            else:
                plan_ownership_context += (
                    "This plan has no tasks associated with it. Add tasks to it! "
                )
        else:
            plan_ownership_context = "You do not own any plans. "

        # participation
        if self.agent.participating_in_plan:
            plan = self.agent.participating_in_plan
            plan_participation_context = (
                "You are participating in the following plans owned by other people: "
            )
            for plan_id in plan.participants:
                if plan_id == self.agent.owned_plan.id:
                    continue
                plan_participation_context += str(plan) + " "
                if plan.tasks:
                    plan_participation_context += (
                        "These are the current tasks associated with this plan: "
                        + ", ".join(map(str, plan.tasks))
                    )
                else:
                    plan_participation_context += "This plan has no tasks associated with it. Wait for the owner to add tasks. "

        else:
            plan_participation_context = (
                "You are not participating in any plans owned by other people. "
            )
            if not self.agent.owned_plan:
                plan_participation_context += "As you also do not own any plans, consider to either former a new plan or join an existing one. "

        # assigned tasks
        if self.agent.task:
            assigned_tasks_context = (
                "You are responsible to execute the following tasks: "
            )

            assigned_tasks_context += str(self.agent.task) + " "
        else:
            assigned_tasks_context = "You are not responsible to execute any task. Consider taking on responsibility for available tasks. "

        plans_description = (
            "Plans: "
            + plan_ownership_context
            + "\n"
            + plan_participation_context
            + "\n"
            + assigned_tasks_context
        )

        # TODO: ensure this by adaptive tool calls and improved prompting
        # has_plan = "You ALREADY HAVE a plan." if plan_id else "You do not have a plan"
        # has_three_tasks = (
        #     "YOU ALREADY HAVE 3 tasks."
        #     if plan_obj and len(plan_obj.get_tasks()) >= 3
        #     else "You do not have 3 tasks."
        # )

        # plan_restrictions = (
        #     f"IMPORTANT: You can ONLY HAVE ONE PLAN {has_plan}.\n "
        #     + f"If you have a plan always add at least one task, at most 3. {has_three_tasks} \n "
        #     + "Once you have a plan and tasks, start moving towards the target of the task. \n"
        # )

        return plans_description
