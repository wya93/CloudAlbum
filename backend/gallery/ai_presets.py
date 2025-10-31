"""AI 标签预设集合，便于复用与扩展。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List


@dataclass(frozen=True)
class LabelPreset:
    """标签预设定义。"""

    key: str
    language: str
    labels: List[str]

    def texts(self) -> List[str]:
        """返回标签文本。"""

        return list(self.labels)


_DEFAULT_PRESETS: Dict[str, LabelPreset] = {
    "zh": LabelPreset(
        key="default_zh",
        language="zh",
        labels=[
            "人像",
            "自拍",
            "宠物",
            "狗",
            "猫",
            "海滩",
            "山",
            "森林",
            "城市夜景",
            "街道",
            "建筑",
            "美食",
            "咖啡",
            "花卉",
            "日出",
            "日落",
            "天空",
            "星空",
            "雪",
            "雨天",
            "室内",
            "聚会",
            "婚礼",
            "运动",
            "汽车",
            "火车",
            "飞机",
            "湖泊",
            "河流",
            "沙漠",
        ],
    )
}


def get_labels(language: str = "zh") -> List[str]:
    """根据语言获取标签列表，若缺失则回退中文默认集合。"""

    preset = _DEFAULT_PRESETS.get(language)
    if preset is None:
        preset = _DEFAULT_PRESETS["zh"]
    return preset.texts()


def register_preset(preset: LabelPreset) -> None:
    """注册额外预设，供外部扩展。"""

    _DEFAULT_PRESETS[preset.language] = preset


def available_languages() -> Iterable[str]:
    """列出当前可用的预设语言。"""

    return _DEFAULT_PRESETS.keys()
