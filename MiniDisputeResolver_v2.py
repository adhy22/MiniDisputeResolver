# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
MiniDisputeResolver v2 — fixed validator
================================================
Fixes the 13 Nov 2026 GenLayer rejection of v1:

v1 flaw (reviewer was right):
  validator_fn only checked ("CLAIMANT" in text) or ("RESPONDENT" in text).
  Both labels pass, so opposite final decisions could both pass consensus.
  decide() then did: winner = CLAIMANT if "CLAIMANT" in raw else RESPONDENT.
  No independent check of the reasoning, evidence, or binding to the winner.

v2 fix — three independent layers, all must pass:
  1. STRUCTURED OUTPUT: the LLM must return JSON only:
     {winner, winner_score, loser_score, evidence_quote, reason}
  2. DETERMINISTIC BINDING (no LLM needed):
     - winner is exactly CLAIMANT or RESPONDENT, winner_score > loser_score
     - evidence_quote is a real, >=10-char quote taken from the WINNING
       side's claim/evidence only — not from the losing side
     - reason names the winning side and is >=20 chars
     If any of these fail, the ruling is rejected.
  3. INDEPENDENT RE-JUDGEMENT (the GenLayer pattern):
     validator_fn() calls leader_fn() again itself — a fresh, independent
     LLM judgement on the same claims — parses it with the same
     deterministic checks, and only accepts if its winner == leader winner.
     This is the "Partial Field Matching" equivalence pattern from the
     GenLayer docs: only the decision field (winner) must agree, the
     wording/reason may differ.

  Plus, to answer "thin wrapper / not reusable":
  - Multiple disputes, each with its own id, stored in TreeMap[u256, Dispute]
  - Separate submission per side, with sender address + evidence recorded
  - Status lifecycle: OPEN -> READY -> DECIDED -> CONFIRMED_ON_APPEAL /
    DECIDED_ON_APPEAL
  - appeal(): one appeal per dispute, a second stricter independent
    panel re-judges; a different winner overturns the ruling.

Deploy / test in GenLayer Studio (Studionet):
  1. Deploy this file (new contract, new address — do NOT reuse the v1 address).
  2. create_dispute("...") -> dispute_id
  3. submit_claim(id, "CLAIMANT", "...claim...", "...evidence...")
  4. submit_claim(id, "RESPONDENT", "...claim...", "...evidence...")
  5. decide(id) -> get_ruling(id)
  6. appeal(id, "...why the first ruling was wrong...") -> get_ruling(id)

Negative test that v1 would have passed and v2 must reject:
  - a claim text that contains BOTH words "CLAIMANT" and "RESPONDENT"
    in a confusing way, or an LLM answer naming both sides as winner.
    v2 rejects it in _parse_ruling / _check_evidence_binding, because
    exactly one winner + a quote from that side only is required.
"""

from dataclasses import dataclass
import json

from genlayer import *


# ---------------------------------------------------------------------------
# Helpers — deterministic, no LLM. These run the same on every validator.
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    return " ".join(str(text).lower().split())


def _parse_ruling(raw) -> dict | None:
    """Parse + deterministically validate a leader/validator JSON ruling.

    Returns the ruling dict, or None if it is not a well-formed ruling.
    This is what makes an opposite label unable to pass: a ruling must
    name exactly one winner, with a higher score, a real evidence quote
    and a real reason — not just contain the word CLAIMANT/RESPONDENT.
    """
    # exec_prompt(response_format="json") may already return a dict,
    # while a plain exec_prompt returns a JSON string — accept both.
    if isinstance(raw, dict):
        data = raw
    else:
        try:
            text = str(raw).strip()
            if text.startswith("```"):
                text = text.replace("```json", "").replace("```", "").strip()
            data = json.loads(text)
        except Exception:
            return None

    if not isinstance(data, dict):
        return None

    winner = data.get("winner")
    if winner not in ("CLAIMANT", "RESPONDENT"):
        return None

    try:
        winner_score = int(data.get("winner_score"))
        loser_score = int(data.get("loser_score"))
    except Exception:
        return None
    if not (0 <= loser_score < winner_score <= 100):
        return None

    quote = str(data.get("evidence_quote") or "").strip()
    reason = str(data.get("reason") or "").strip()
    if len(quote) < 10 or len(reason) < 20:
        return None
    # The reason must name the side it says won — otherwise it is not
    # bound to the winner at all.
    if winner.lower() not in reason.lower():
        return None

    return {
        "winner": winner,
        "winner_score": winner_score,
        "loser_score": loser_score,
        "evidence_quote": quote,
        "reason": reason,
    }


def _check_evidence_binding(ruling: dict, dispute) -> bool:
    """The evidence quote must come from the WINNING side only.

    This binds the winner to actual evidence. A ruling that says
    CLAIMANT won but quotes only the respondent's text fails here,
    and vice versa. A generic quote that appears in both sides also fails.
    """
    quote = _norm(ruling["evidence_quote"])
    if len(quote) < 10:
        return False

    if ruling["winner"] == "CLAIMANT":
        winning_text = _norm(dispute.claimant_claim + " " + dispute.claimant_evidence)
        losing_text = _norm(dispute.respondent_claim + " " + dispute.respondent_evidence)
    else:
        winning_text = _norm(dispute.respondent_claim + " " + dispute.respondent_evidence)
        losing_text = _norm(dispute.claimant_claim + " " + dispute.claimant_evidence)

    return quote in winning_text and quote not in losing_text


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

@allow_storage
@dataclass
class Dispute:
    description: str
    claimant: str
    respondent: str
    claimant_claim: str
    respondent_claim: str
    claimant_evidence: str
    respondent_evidence: str
    status: str  # OPEN | READY | DECIDED | CONFIRMED_ON_APPEAL | DECIDED_ON_APPEAL
    winner: str
    winner_score: u256
    loser_score: u256
    evidence_quote: str
    ruling_reason: str
    appealed: bool
    appeal_reason: str


class MiniDisputeResolver(gl.Contract):
    dispute_counter: u256
    disputes: TreeMap[u256, Dispute]

    def __init__(self):
        self.dispute_counter = u256(0)

    # ------------------------------------------------------------------
    # Create + submit (reusable: one contract, many disputes)
    # ------------------------------------------------------------------

    @gl.public.write
    def create_dispute(self, description: str) -> u256:
        dispute_id = self.dispute_counter
        self.dispute_counter = self.dispute_counter + u256(1)
        self.disputes[dispute_id] = Dispute(
            description=description,
            claimant=str(gl.message.sender_address),
            respondent="",
            claimant_claim="",
            respondent_claim="",
            claimant_evidence="",
            respondent_evidence="",
            status="OPEN",
            winner="",
            winner_score=u256(0),
            loser_score=u256(0),
            evidence_quote="",
            ruling_reason="",
            appealed=False,
            appeal_reason="",
        )
        return dispute_id

    @gl.public.write
    def submit_claim(self, dispute_id: u256, side: str, claim: str, evidence: str) -> None:
        dispute = self.disputes[dispute_id]
        if dispute.status != "OPEN":
            print("dispute is not open for submissions")
            return
        if side not in ("CLAIMANT", "RESPONDENT"):
            print("side must be CLAIMANT or RESPONDENT")
            return
        if len(claim.strip()) < 10 or len(evidence.strip()) < 5:
            print("claim and evidence must not be empty")
            return

        sender = str(gl.message.sender_address)
        if side == "CLAIMANT":
            if dispute.claimant_claim:
                print("claimant already submitted")
                return
            dispute.claimant = sender
            dispute.claimant_claim = claim
            dispute.claimant_evidence = evidence
        else:
            if dispute.respondent_claim:
                print("respondent already submitted")
                return
            dispute.respondent = sender
            dispute.respondent_claim = claim
            dispute.respondent_evidence = evidence

        if dispute.claimant_claim and dispute.respondent_claim:
            dispute.status = "READY"
        self.disputes[dispute_id] = dispute

    # ------------------------------------------------------------------
    # Judging — the fixed part
    # ------------------------------------------------------------------

    def _judge_prompt(self, dispute, is_appeal: bool) -> str:
        role = (
            "You are an appeal panel re-examining a disputed ruling. "
            "Do not copy the first ruling. Look for inconsistencies and "
            "for which side's evidence is actually stronger."
            if is_appeal
            else "You are a fair, impartial judge for a small on-chain dispute."
        )
        return (
            role + "\n"
            "Dispute: " + dispute.description + "\n"
            "CLAIMANT says: " + dispute.claimant_claim[:1500] + "\n"
            "CLAIMANT evidence: " + dispute.claimant_evidence[:1000] + "\n"
            "RESPONDENT says: " + dispute.respondent_claim[:1500] + "\n"
            "RESPONDENT evidence: " + dispute.respondent_evidence[:1000] + "\n"
            "Decide who should win based on the stronger, more consistent "
            "argument AND the evidence quoted.\n"
            "Return ONLY valid JSON, no markdown, no extra text:\n"
            '{"winner": "CLAIMANT" or "RESPONDENT", '
            '"winner_score": 0-100, "loser_score": 0-100, '
            '"evidence_quote": "an exact short quote (at least 10 characters) '
            'copied from the WINNING side\'s claim or evidence", '
            '"reason": "1-2 sentences naming the winner and the evidence that '
            'made them win"}\n'
            "Rules: winner_score must be greater than loser_score. "
            "evidence_quote must be copied from the winning side only."
        )

    def _run_judgement(self, dispute, is_appeal: bool) -> dict | None:
        """One full nondet round: leader proposes, validators independently
        re-judge and must agree on the winner. Returns the agreed ruling,
        or None if consensus / validation fails (dispute stays undecided,
        so decide() can be retried instead of storing a bad ruling)."""

        def leader_fn():
            return gl.nondet.exec_prompt(
                self._judge_prompt(dispute, is_appeal),
                response_format="json",
            )

        def validator_fn(leader_result) -> bool:
            # Layer 1: leader must be a real Return, not an error.
            if not isinstance(leader_result, gl.vm.Return):
                return False
            # Layer 2: deterministic parse + evidence binding of the leader.
            leader_ruling = _parse_ruling(leader_result.calldata)
            if leader_ruling is None:
                return False
            if not _check_evidence_binding(leader_ruling, dispute):
                return False
            # Layer 3: INDEPENDENT re-judgement. The validator runs the
            # same prompt itself and must reach the SAME winner.
            # This is the fix: in v1 this step did not exist — the
            # validator only checked that a label word was present.
            my_raw = leader_fn()
            my_ruling = _parse_ruling(my_raw)
            if my_ruling is None:
                return False
            if not _check_evidence_binding(my_ruling, dispute):
                return False
            return my_ruling["winner"] == leader_ruling["winner"]

        result = gl.vm.run_nondet_unsafe(leader_fn, validator_fn)
        # run_nondet_unsafe may return a gl.vm.Return wrapping the
        # leader output, or the leader output itself — handle both.
        raw = result.calldata if isinstance(result, gl.vm.Return) else result
        ruling = _parse_ruling(raw)
        if ruling is None:
            return None
        if not _check_evidence_binding(ruling, dispute):
            return None
        return ruling

    @gl.public.write
    def decide(self, dispute_id: u256) -> None:
        dispute = self.disputes[dispute_id]
        if dispute.status != "READY":
            print("dispute must be READY (both sides submitted) before decide")
            return

        ruling = self._run_judgement(dispute, is_appeal=False)
        if ruling is None:
            # Do NOT store a ruling on failed consensus/validation.
            print("consensus or validation failed, ruling not stored — retry decide")
            return

        dispute.winner = ruling["winner"]
        dispute.winner_score = u256(ruling["winner_score"])
        dispute.loser_score = u256(ruling["loser_score"])
        dispute.evidence_quote = ruling["evidence_quote"]
        dispute.ruling_reason = ruling["reason"]
        dispute.status = "DECIDED"
        self.disputes[dispute_id] = dispute

    @gl.public.write
    def appeal(self, dispute_id: u256, appeal_reason: str) -> None:
        dispute = self.disputes[dispute_id]
        if dispute.status != "DECIDED":
            print("only a DECIDED dispute can be appealed")
            return
        if dispute.appealed:
            print("this dispute has already been appealed once")
            return
        if len(appeal_reason.strip()) < 10:
            print("appeal needs a reason of at least 10 characters")
            return

        dispute.appealed = True
        dispute.appeal_reason = appeal_reason
        ruling = self._run_judgement(dispute, is_appeal=True)
        if ruling is None:
            print("appeal consensus failed, original ruling stands")
            self.disputes[dispute_id] = dispute
            return

        if ruling["winner"] != dispute.winner:
            dispute.winner = ruling["winner"]
            dispute.winner_score = u256(ruling["winner_score"])
            dispute.loser_score = u256(ruling["loser_score"])
            dispute.evidence_quote = ruling["evidence_quote"]
            dispute.ruling_reason = ruling["reason"]
            dispute.status = "DECIDED_ON_APPEAL"
        else:
            dispute.status = "CONFIRMED_ON_APPEAL"
        self.disputes[dispute_id] = dispute

    # ------------------------------------------------------------------
    # Views
    # ------------------------------------------------------------------

    @gl.public.view
    def get_dispute(self, dispute_id: u256) -> dict:
        d = self.disputes[dispute_id]
        return {
            "id": int(dispute_id),
            "description": d.description,
            "claimant": d.claimant,
            "respondent": d.respondent,
            "status": d.status,
            "winner": d.winner,
            "appealed": d.appealed,
        }

    @gl.public.view
    def get_ruling(self, dispute_id: u256) -> dict:
        d = self.disputes[dispute_id]
        return {
            "description": d.description,
            "decided": d.status in ("DECIDED", "CONFIRMED_ON_APPEAL", "DECIDED_ON_APPEAL"),
            "status": d.status,
            "winner": d.winner,
            "winner_score": int(d.winner_score),
            "loser_score": int(d.loser_score),
            "evidence_quote": d.evidence_quote,
            "ruling_reason": d.ruling_reason,
            "appealed": d.appealed,
            "appeal_reason": d.appeal_reason,
        }
