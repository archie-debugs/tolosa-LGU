import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)

from frontend.admin.stage_panel import build_stage_section
from tests.test_registration_dialogs import DummyPage, click, find_button, texts, walk

ORDINANCE_STAGES = ["Filed", "First Reading", "In Committee", "Committee Report", "Second Reading", "Third Reading",
                    "Approved", "Sent to the Mayor", "Signed", "Vetoed", "Lapsed into Law", "Provincial Review", "Posted",
                    "Withdrawn", "Tabled", "Lost"]


def stage_payload(stage="First Reading", allowed=("In Committee", "Second Reading", "Withdrawn"), number=None, history=None):
    return {
        "is_measure": True, "kind": "ordinance", "stage": stage, "allowed": list(allowed), "stages": ORDINANCE_STAGES,
        "enacted_stage": "Approved", "document_number": number, "series_year": None,
        "history": history if history is not None else [
            {"id": 1, "stage": stage, "effective_on": "2026-10-20", "committee": None, "note": "Registered at this stage",
             "is_correction": False, "changed_by": "admin"},
        ],
    }


class FakeApi:
    def __init__(self, payload=None):
        self.payload = payload or stage_payload()
        self.calls = []
        self.fail_with = None

    def __call__(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if method == "GET" and path == "/documents/7/stage":
            return self.payload
        if path == "/council/committees?active_only=true":
            return [{"id": 3, "name": "Committee on Health"}]
        if method == "POST":
            if self.fail_with:
                raise Exception(self.fail_with)
            body = kwargs["json"]
            return stage_payload(stage=body["stage"], allowed=[], history=[
                {"id": 2, "stage": body["stage"], "effective_on": body.get("effective_on") or "2026-10-22", "committee": None,
                 "note": body.get("note") or body.get("reason"), "is_correction": path.endswith("corrections"), "changed_by": "admin"},
            ])
        raise AssertionError((method, path))

    def posted(self):
        return [(path, kwargs["json"]) for method, path, kwargs in self.calls if method == "POST"]


def dropdown(section, label):
    return next(c for c in walk(section) if type(c).__name__ == "Dropdown" and c.label == label)


def text_field(section, label):
    return next(c for c in walk(section) if type(c).__name__ == "TextField" and c.label == label)


def choose(control, value):
    control.value = value
    (getattr(control, "on_change", None) or getattr(control, "on_select", None))(None)


def press(section, text):
    button = find_button(section, text)
    assert button is not None, text
    click(button)


def open_section(api=None, can_change=True):
    api = api or FakeApi()
    saved = []
    section = build_stage_section(DummyPage(), api, 7, can_change=can_change, on_saved=lambda: saved.append(True))
    return section, api, saved


def test_documents_that_are_not_measures_have_no_stage_section():
    api = FakeApi({"is_measure": False, "stage": None, "allowed": [], "stages": [], "history": []})
    assert open_section(api)[0] is None


def test_the_section_shows_the_stage_and_its_history_and_readers_cannot_change_it():
    section, _, _ = open_section(can_change=False)

    assert "Stage" in texts(section) and "First Reading" in texts(section)
    assert "Registered at this stage" in texts(section)
    assert find_button(section, "Change stage") is None and find_button(section, "Correct a mistake") is None


def test_referring_a_measure_asks_for_the_committee():
    section, api, saved = open_section()
    press(section, "Change stage")
    choose(dropdown(section, "New stage"), "In Committee")
    committee = dropdown(section, "Committee")

    assert committee.visible and [option.text for option in committee.options] == ["Committee on Health"]
    committee.value = "3"
    text_field(section, "Date it happened").value = "2026-10-21"
    press(section, "Save stage")

    assert api.posted() == [("/documents/7/stage", {"stage": "In Committee", "effective_on": "2026-10-21", "committee_id": 3, "note": None})]
    assert saved == [True] and "Stage changed to In Committee." in texts(section)


def test_approval_asks_for_the_number_and_a_bad_date_is_caught_first():
    api = FakeApi(stage_payload(stage="Third Reading", allowed=["Approved", "Withdrawn"]))
    section, api, _ = open_section(api)
    press(section, "Change stage")
    choose(dropdown(section, "New stage"), "Approved")
    number = text_field(section, "Ordinance number")
    assert number.visible

    text_field(section, "Date it happened").value = "21/10/2026"
    press(section, "Save stage")
    assert api.posted() == [] and "The date must look like 2026-10-22." in texts(section)

    text_field(section, "Date it happened").value = ""
    number.value = "6"
    press(section, "Save stage")
    assert api.posted() == [("/documents/7/stage", {"stage": "Approved", "document_number": "6", "note": None})]


def test_a_correction_needs_a_reason_and_offers_every_stage():
    section, api, _ = open_section()
    press(section, "Correct a mistake")
    stage = dropdown(section, "Correct stage")
    assert [option.key or option.text for option in stage.options] == ORDINANCE_STAGES

    choose(stage, "Filed")
    press(section, "Save correction")
    assert api.posted() == [] and "Say why the stage is being corrected." in texts(section)

    text_field(section, "Reason (required)").value = "Registered at the wrong reading"
    press(section, "Save correction")
    assert api.posted() == [("/documents/7/stage/corrections", {"stage": "Filed", "reason": "Registered at the wrong reading"})]
    assert "Correction" in texts(section)


def test_a_refused_change_shows_the_backend_s_reason():
    api = FakeApi()
    api.fail_with = "The date can't be before 2026-10-20, when it became First Reading."
    section, _, saved = open_section(api)
    press(section, "Change stage")
    choose(dropdown(section, "New stage"), "Second Reading")
    press(section, "Save stage")

    assert saved == [] and api.fail_with in texts(section)
