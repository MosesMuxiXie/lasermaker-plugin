"""Build editable demonstration projects from the public synthetic fixture."""
import json
from pathlib import Path

from lasermaker_agent.sample import convert_legacy, coupon_design
from lasermaker_agent.service import Service


def main():
    root = Path(__file__).resolve().parent.parent
    source = json.loads((root / "tests/fixtures/synthetic-six-part.json").read_text(encoding="utf-8"))
    service = Service()
    for name, title, design in (("synthetic-six-panel", "公开合成六板测试样例", convert_legacy(source)),
                                ("slot-coupon", "独立插槽试切片", coupon_design(source))):
        project = root / "examples" / name / "project"
        if not (project / "project.json").exists():
            service.call("create_project", {"root": str(project), "name": title, "design": design})
        result = service.call("export_delivery", {"root": str(project)})
        result['artifacts'] = {k: Path(v).relative_to(project.parent).as_posix() for k,v in result['artifacts'].items()}
        (project.parent / "delivery.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        print(json.dumps({"example": name, "project": str(project), "artifacts": result["artifacts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
