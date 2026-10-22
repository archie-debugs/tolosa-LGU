import frontend.admin.app  # noqa: F401  (applies the flet compatibility shims)
import flet as ft

from tests.test_council_page import button, dialog, texts, walk
from tests.test_council_sessions_page import FakeApi, build, business, detail, open_first_session, save

REFERRAL = {"outcome": "Referred to committee", "committee": True, "number": False}
THIRD = {"outcome": "Approved on third reading", "committee": False, "number": True}
DEFERRED = {"outcome": "Deferred", "committee": False, "number": False}


def measure_item(item_id=21, outcome=None, vote=None, outcome_history=None, vote_history=None, has_number=False):
    return {"id": item_id, "section": "first_reading", "title": "An ordinance regulating tricycles",
            "document": {"id": 7, "tracking_number": "DOC-000007", "title": "An ordinance regulating tricycles",
                         "document_type": "Ordinance", "stage": "Filed", "is_measure": True, "has_number": has_number},
            "outcome": outcome, "outcome_history": outcome_history or ([outcome] if outcome else []),
            "vote": vote, "vote_history": vote_history or ([vote] if vote else []),
            "outcome_choices": [REFERRAL, THIRD, DEFERRED]}


def speech_item(item_id=22):
    return {"id": item_id, "section": "other", "title": "Privilege speech of Hon. Cruz", "document": None, "outcome": None,
            "outcome_history": [], "vote": None, "vote_history": [], "outcome_choices": [DEFERRED]}


class BusinessApi(FakeApi):
    def __init__(self, held=False, items=None, suggestions=None, committees=None):
        super().__init__(detail("Held" if held else "Draft"),
                         business(editable=not held, items=items or {"first_reading": [measure_item()], "other": [speech_item()]}))
        self.suggestions = suggestions or []

    def __call__(self, method, path, **kwargs):
        if path.endswith("/business/suggestions"):
            self.calls.append((method, path, None))
            return self.suggestions
        if path.endswith("/business/documents"):
            self.calls.append((method, path, kwargs.get("params")))
            return [{"id": 9, "tracking_number": "DOC-000009", "title": "Letter from the DILG"}]
        if path.startswith("/council/committees"):
            return [{"id": 5, "name": "Committee on Health"}]
        return super().__call__(method, path, **kwargs)


def opened(api, can_manage=True):
    page, view = build(api, can_manage=can_manage)
    open_first_session(view)
    return page, view


def text_button(view, label, index=0):
    return [item for item in walk(view) if isinstance(item, ft.TextButton) and
            (getattr(item, "text", None) == label or getattr(item, "content", None) == label)][index]


def test_the_order_of_business_lists_every_section_in_order_with_numbered_items():
    page, view = opened(BusinessApi())
    shown = texts(view)

    assert "1. Call to order" in shown and "9. Adjournment" in shown
    assert shown.index("4. First reading and referral") < shown.index("4.1  An ordinance regulating tricycles")
    assert "8.1  Privilege speech of Hon. Cruz" in shown
    assert "DOC-000007 · Ordinance · at Filed" in shown


def test_an_item_is_added_from_a_document_search_or_by_title():
    api = BusinessApi()
    page, view = opened(api)

    button(view, "Add item").on_click(None)
    form = dialog(page)
    search = next(item for item in walk(form.content) if isinstance(item, ft.TextField))
    search.value = "DILG"
    button(form.content, "Find").on_click(None)
    save(form, "Add")

    assert ("GET", "/council/sessions/4/business/documents", {"search": "DILG"}) in api.calls
    assert ("POST", "/council/sessions/4/business/items", {"section": "other", "document_id": 9}) in api.calls


def test_suggested_items_are_added_only_when_ticked():
    suggestions = [{"section": "first_reading", "section_label": "First reading and referral", "reason": "At Filed",
                    "document": {"id": 30, "tracking_number": "DOC-000030", "title": "A resolution"}},
                   {"section": "unfinished", "section_label": "Unfinished business", "reason": "Deferred at the 1st Regular Session",
                    "document": {"id": 31, "tracking_number": "DOC-000031", "title": "An ordinance"}}]
    api = BusinessApi(suggestions=suggestions)
    page, view = opened(api)

    button(view, "Suggested items").on_click(None)
    form = dialog(page)
    boxes = [item for item in walk(form.content) if isinstance(item, ft.Checkbox)]
    boxes[1].value = False
    save(form, "Add selected")

    posts = [call for call in api.calls if call[0] == "POST"]
    assert posts == [("POST", "/council/sessions/4/business/items", {"section": "first_reading", "document_id": 30})]


def test_an_outcome_asks_for_the_committee_or_the_enacted_number_only_when_needed():
    api = BusinessApi()
    page, view = opened(api)

    text_button(view, "Outcome").on_click(None)
    form = dialog(page)
    outcome, committee = [item for item in walk(form.content) if isinstance(item, ft.Dropdown)][:2]
    number = next(item for item in walk(form.content) if isinstance(item, ft.TextField) and item.label == "Enacted number")
    outcome.value = "Referred to committee"
    handler = getattr(outcome, "on_select", None) or getattr(outcome, "on_change", None)
    handler(None)
    assert committee.visible and not number.visible
    committee.value = "5"
    save(form)

    assert ("PUT", "/council/sessions/4/business/items/21/outcome",
            {"outcome": "Referred to committee", "committee_id": 5, "note": None}) in api.calls


def test_a_held_sessions_outcome_is_corrected_with_a_reason():
    first = {"outcome": "Deferred", "note": None, "stages": [], "is_correction": False, "recorded_by": "clerk"}
    api = BusinessApi(held=True, items={"first_reading": [measure_item(outcome=first)]})
    page, view = opened(api)

    assert not [item for item in walk(view) if isinstance(item, ft.IconButton) and item.tooltip == "Move up"]
    text_button(view, "Correct outcome").on_click(None)
    form = dialog(page)
    outcome = next(item for item in walk(form.content) if isinstance(item, ft.Dropdown))
    reason = next(item for item in walk(form.content) if isinstance(item, ft.TextField) and item.label == "Reason (required)")
    outcome.value = "Approved on third reading"
    (getattr(outcome, "on_select", None) or getattr(outcome, "on_change", None))(None)
    save(form)
    assert form.open is True and not [call for call in api.calls if call[0] == "POST"]

    reason.value = "The minutes say it was approved"
    number = next(item for item in walk(form.content) if isinstance(item, ft.TextField) and item.label == "Enacted number")
    number.value = "15"
    save(form)
    assert ("POST", "/council/sessions/4/business/items/21/outcome/corrections",
            {"outcome": "Approved on third reading", "document_number": "15", "series_year": 2026,
             "reason": "The minutes say it was approved"}) in api.calls


def test_a_nominal_vote_sends_each_members_vote():
    api = BusinessApi()
    page, view = opened(api)

    text_button(view, "Vote").on_click(None)
    form = dialog(page)
    method = next(item for item in walk(form.content) if isinstance(item, ft.Dropdown) and item.label == "Vote")
    method.value = "Nominal"
    (getattr(method, "on_select", None) or getattr(method, "on_change", None))(None)
    santos, cruz, lim = [item for item in walk(form.content) if isinstance(item, ft.Dropdown) and item.label.startswith("Hon.")]
    santos.value, cruz.value = "Yes", "No"
    save(form)

    assert ("PUT", "/council/sessions/4/business/items/21/vote", {"method": "Nominal", "result": "Carried", "members": [
        {"member_id": 10, "vote": "Yes"}, {"member_id": 11, "vote": "No"}]}) in api.calls


def test_votes_and_corrections_show_on_the_item():
    vote = {"method": "Voice", "yes": 3, "no": 0, "abstain": 0, "result": "Carried", "members": [], "is_correction": False}
    fixed = {**vote, "yes": 2, "no": 1, "is_correction": True, "recorded_by": "clerk", "note": "Recount"}
    api = BusinessApi(held=True, items={"first_reading": [measure_item(vote=fixed, vote_history=[fixed, vote])]})
    page, view = opened(api)

    shown = texts(view)
    assert "Voice vote 2-1-0, Carried" in shown
    assert "Vote corrected to Voice vote 2-1-0, Carried by clerk: Recount" in shown


def test_marking_held_warns_about_items_without_an_outcome():
    api = BusinessApi()
    api.business["without_outcome"] = 2
    page, view = opened(api)

    button(view, "Mark as held").on_click(None)

    assert "2 item(s) in the order of business have no outcome." in texts(dialog(page).content)


def test_readers_see_the_order_of_business_without_any_way_to_change_it():
    page, view = opened(BusinessApi(), can_manage=False)

    assert "4.1  An ordinance regulating tricycles" in texts(view)
    assert not [item for item in walk(view) if isinstance(item, (ft.TextButton, ft.IconButton)) and
                (getattr(item, "text", None) or getattr(item, "content", None) or getattr(item, "tooltip", None)) in
                ("Outcome", "Vote", "Move up", "Remove", "Correct outcome")]
