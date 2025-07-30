from engine.context.base import BaseContext


class HungerContext(BaseContext):
    def build(self, **kwargs) -> str:
        if self.agent.energy_level <= self.agent.hunger:
            hunger_description = (
                f"Energy level: Your current energy level is {self.agent.energy_level}. "
                "You are starving and need to find and consume resources immediately."
            )
        else:
            hunger_description = (
                f"Energy level: Your current energy level is {self.agent.energy_level}. "
                "You are not starving. You MUST NOT harvest resources at this time. Instead, you should communicate, cooperate, or explore."
            )
        return hunger_description
