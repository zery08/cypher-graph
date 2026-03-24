"""
tools 패키지 자동 로딩
이 패키지의 모든 모듈에서 TOOL_SPEC + run() 을 자동 탐색하여 반환한다.
"""
import importlib
import pkgutil
import pathlib
import logging
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class ToolDef:
    """단일 tool 정의"""
    name: str          # OpenAI function name
    label: str         # 사람이 읽는 한글 레이블
    spec: dict         # OpenAI function spec (type: "function", function: {...})
    run: Callable      # run(args: dict) -> str


def load_all_tools() -> list[ToolDef]:
    """
    tools 패키지 내 모든 모듈을 스캔하여 TOOL_SPEC + run() 을 갖는 것만 수집한다.
    새 tool 파일을 추가하면 자동으로 포함된다.
    """
    tools: list[ToolDef] = []
    pkg_dir = pathlib.Path(__file__).parent

    for _, mod_name, _ in pkgutil.iter_modules([str(pkg_dir)]):
        if mod_name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f".{mod_name}", package=__name__)
            if hasattr(mod, "TOOL_SPEC") and hasattr(mod, "run"):
                spec: dict = mod.TOOL_SPEC
                fn_name: str = spec["function"]["name"]
                label: str = getattr(mod, "TOOL_LABEL", fn_name)
                tools.append(ToolDef(name=fn_name, label=label, spec=spec, run=mod.run))
                logger.debug(f"tool 로드: {fn_name} ({label})")
            else:
                logger.debug(f"tool 스킵 (TOOL_SPEC 또는 run 없음): {mod_name}")
        except Exception as e:
            logger.warning(f"tool 모듈 로드 실패 ({mod_name}): {e}")

    logger.info(f"tool {len(tools)}개 로드 완료: {[t.name for t in tools]}")
    return tools
