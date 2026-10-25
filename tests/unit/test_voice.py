import asyncio
from backend.app.config import Settings
from backend.app.providers.meta_voice import TurnAssembler
from backend.app.vision.engine import VisionEngine
from backend.app.voice import VoicePipeline
from shared.contracts import RequestAction
from tests.unit.fakes import Script, face, packet


class FakeSession:
    def __init__(self, engine):
        self.session_id, self.engine = "s_test", engine
    def now_ms(self):
        return 5000


def pipeline():
    s = Script()
    e = VisionEngine("s_test", s.detect, s.feature)
    s.frame = [face("A", 100, 100)]
    for i in range(1, 40):
        e.step(packet(i))
    st = Settings(); st.intent_provider = "muse"
    vp = VoicePipeline(st, FakeSession(e))
    vp.llm = vp.fallback = None  # no network in unit tests
    vp._audio_t0_ms, vp._gen = 0, 1
    vp.sync_decisions = True
    submitted = []
    e.submit = submitted.append
    return vp, submitted


def test_assembler_emits_partials_then_one_final():
    a = TurnAssembler()
    assert a.feed({"type": "speechStart", "turnId": 3, "audioProcessedMs": 500}) is None
    assert a.feed({"type": "transcript", "transcript": "please", "final": False, "audioProcessedMs": 800})[0] == "partial"
    a.feed({"type": "speechEnd", "turnId": 3, "audioProcessedMs": 1500})
    f = a.feed({"type": "speechComplete", "turnId": 3, "transcript": "please blur me", "audioProcessedMs": 2100})
    assert f == ("final", "3", 500, 1500, "please blur me")
    assert a.feed({"type": "speechComplete", "turnId": 3, "transcript": "x", "audioProcessedMs": 2200}) is None

def test_partial_refusal_acts_early_once_and_final_does_not_repeat():
    vp, sub = pipeline()
    asyncio.run(vp._on_turn(("partial", "0", 600, 1500, "please blur")))
    assert sub == []
    asyncio.run(vp._on_turn(("partial", "0", 600, 1800, "please blur me")))
    assert len(sub) == 1 and sub[0].action == RequestAction.PROTECT
    asyncio.run(vp._on_turn(("partial", "0", 600, 1900, "please blur me now")))
    asyncio.run(vp._on_turn(("final", "0", 600, 2000, "please blur me now")))
    assert len(sub) == 1

def test_partial_consent_never_acts_early():
    vp, sub = pipeline()
    asyncio.run(vp._on_turn(("partial", "1", 600, 1500, "unblur me")))
    assert sub == []
    asyncio.run(vp._on_turn(("final", "1", 600, 1700, "unblur me")))
    assert len(sub) == 1 and sub[0].action == RequestAction.UNPROTECT

def test_final_that_changes_meaning_is_decided_again():
    vp, sub = pipeline()
    asyncio.run(vp._on_turn(("partial", "2", 600, 1500, "blur me")))
    asyncio.run(vp._on_turn(("final", "2", 600, 1700, "unblur me")))
    assert [r.action for r in sub] == [RequestAction.PROTECT, RequestAction.UNPROTECT]

def test_turn_ids_do_not_collide_after_reconnect():
    vp, sub = pipeline()
    asyncio.run(vp._on_turn(("final", "0", 600, 1700, "please blur me")))
    vp._gen += 1
    asyncio.run(vp._on_turn(("final", "0", 600, 1700, "please blur me")))
    assert len(sub) == 2
