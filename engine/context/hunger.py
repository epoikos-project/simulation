from engine.context import Context


class HungerContext(Context):
    def build(self) -> str:
        if self.agent.energy_level <= self.agent.hunger:
            hunger_description = f"Energy level: Your current energy level is {self.agent.energy_level}. You are starving and need to find and consume resources immediately. "
        else:
            hunger_description = f"Energy level: Your current energy level is {self.agent.energy_level}. You are not starving, but you should consume resources to maintain your energy level. "
        return (
            hunger_description
            + f"Otherwise you will die after {self.agent.energy_level} actions. "
        )
