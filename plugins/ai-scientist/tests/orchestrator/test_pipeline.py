from pathlib import Path
from unittest.mock import MagicMock
from mcp.lib.orchestrator.pipeline import Pipeline


def test_phase_0_init_creates_dirs_and_config(tmp_path):
    pipeline = Pipeline(
        dispatcher=MagicMock(),
        evaluator=MagicMock(),
        host="claude_code",
        plugin_palace=None,
        project_palace=None,
    )
    pipeline.phase_0_init(
        topic="ridge regression",
        domain="statistical",
        output_dir=tmp_path,
    )
    assert (tmp_path / "config.json").is_file()
    assert (tmp_path / ".checkpoints").is_dir()
    assert (tmp_path / ".palace").is_dir()


def test_phase_0_5_ideation_produces_3_candidates(tmp_path):
    fake_dispatcher = MagicMock(side_effect=[
        {"raw": '{"Name":"a","Title":"A","Short_Hypothesis":"h","Related_Work":"rw","Abstract":"' + "x"*80 + '","Experiments":[{"name":"e","metric":"m"}],"Risks":["r"]}'},
        {"raw": '{"Name":"b","Title":"B","Short_Hypothesis":"h","Related_Work":"rw","Abstract":"' + "x"*80 + '","Experiments":[{"name":"e","metric":"m"}],"Risks":["r"]}'},
        {"raw": '{"Name":"c","Title":"C","Short_Hypothesis":"h","Related_Work":"rw","Abstract":"' + "x"*80 + '","Experiments":[{"name":"e","metric":"m"}],"Risks":["r"]}'},
    ])
    fake_evaluator = MagicMock(return_value={"verdict": "PASS", "reason": ""})
    pipeline = Pipeline(
        dispatcher=fake_dispatcher,
        evaluator=fake_evaluator,
        host="claude_code",
    )
    pipeline.phase_0_init(topic="t", domain="statistical", output_dir=tmp_path)
    candidates = pipeline.phase_0_5_ideation(topic="t", domain="statistical", num_candidates=3)
    assert len(candidates) == 3
    assert (tmp_path / "idea_candidates.json").is_file()


def test_phase_1_dedups_papers(tmp_path):
    fake_dispatcher = MagicMock(return_value={"raw": '[{"title":"A","doi":"10.1/x"},{"title":"A","doi":"10.1/x"}]'})
    pipeline = Pipeline(dispatcher=fake_dispatcher, evaluator=MagicMock(), host="claude_code")
    pipeline.phase_0_init(topic="t", domain="statistical", output_dir=tmp_path)
    papers = pipeline.phase_1_literature(idea={"Title": "ridge"}, sources=["openalex"])
    assert len(papers) == 1


def test_phase_3_codegen_writes_files(tmp_path):
    fake_dispatcher = MagicMock(return_value={"raw": '```python\nprint("ok")\n```'})
    pipeline = Pipeline(dispatcher=fake_dispatcher, evaluator=MagicMock(), host="claude_code")
    pipeline.phase_0_init(topic="t", domain="statistical", output_dir=tmp_path)
    result = pipeline.phase_3_codegen(hypothesis={"hypothesis": "h"}, max_rounds=1)
    assert (tmp_path / "experiment.py").is_file()
    assert (tmp_path / "requirements.txt").is_file()
