from typing import Optional
from collections import defaultdict
from aios_core.contracts.enums import UserReaction
from aios_core.contracts.models import CommunicationExperience

class ExperienceTracker:
    def __init__(self):
        self._experiences: list[CommunicationExperience] = []

    def record_experience(self, experience: CommunicationExperience) -> CommunicationExperience:
        self._experiences.append(experience)
        return experience

    def get_experiences_by_scenario(self, scenario: str) -> list[CommunicationExperience]:
        return [e for e in self._experiences if e.scenario == scenario]

    def get_success_rate(self, scenario: str, style: str) -> float:
        experiences = [e for e in self._experiences if e.scenario == scenario and e.style == style]
        if not experiences:
            return 0.0
        
        success_count = sum(1 for e in experiences if e.user_reaction == UserReaction.ACCEPTED)
        return success_count / len(experiences)

    def get_effective_style(self, scenario: str) -> Optional[str]:
        """在**未被回避**的风格里挑接受率最高的一种。

        回避清单（抵触率 >= 0.5）与推荐名单必须互斥：一种刚被用户抵触的风格
        不允许因为"矮子里拔将军"再次被推荐；一个都没有合格时返回 None，
        由上层使用基础人设语调，而不是把踩雷风格再端上去。
        """

        scenario_exps = self.get_experiences_by_scenario(scenario)
        if not scenario_exps:
            return None

        avoided = set(self.get_avoidance_list(scenario))
        best_style = None
        best_rate = 0.0

        for style in sorted(set(e.style for e in scenario_exps)):
            if style in avoided:
                continue
            rate = self.get_success_rate(scenario, style)
            if rate > best_rate:
                best_rate = rate
                best_style = style

        return best_style

    def get_avoidance_list(self, scenario: str, threshold: float = 0.5) -> list[str]:
        scenario_exps = self.get_experiences_by_scenario(scenario)
        if not scenario_exps:
            return []
            
        style_stats = defaultdict(lambda: {"total": 0, "resisted": 0})
        for e in scenario_exps:
            style_stats[e.style]["total"] += 1
            if e.user_reaction == UserReaction.RESISTED:
                style_stats[e.style]["resisted"] += 1
                
        avoid_list = []
        for style, stats in style_stats.items():
            if stats["resisted"] / stats["total"] >= threshold:
                avoid_list.append(style)
                
        return sorted(avoid_list)

    def evolve_strategy(self, scenario: str) -> dict[str, str | list[str]]:
        effective_style = self.get_effective_style(scenario)
        avoidance_list = self.get_avoidance_list(scenario)
        
        return {
            "scenario": scenario,
            "recommended_style": effective_style or "default",
            "avoid_styles": avoidance_list
        }
