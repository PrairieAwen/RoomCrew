"""可信应用组装参数；不把运行策略和模型秘密混成一个对象。"""

from dataclasses import dataclass, field

from roomcrew.context_compression.policy import CompressionPolicy
from roomcrew.contracts.limits import RunLimits
from roomcrew.security.capabilities import CapabilityPolicy
from roomcrew.skills.registry import SkillPolicy


@dataclass(frozen=True)
class RunOptions:
    limits: RunLimits = field(default_factory=RunLimits)
    compression: CompressionPolicy = field(default_factory=CompressionPolicy)
    capabilities: CapabilityPolicy = field(default_factory=CapabilityPolicy)
    skills: SkillPolicy = field(default_factory=SkillPolicy)
