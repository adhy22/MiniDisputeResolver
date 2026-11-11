# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *


class MiniDisputeResolver(gl.Contract):
    description: str
    claimant_claim: str
    respondent_claim: str
    decided: bool
    winner: str
    ruling_reason: str

    def __init__(self, description: str):
        self.description = description
        self.claimant_claim = ""
        self.respondent_claim = ""
        self.decided = False
        self.winner = ""
        self.ruling_reason = ""

    @gl.public.write
    def submit_claim(self, claimant_claim: str, respondent_claim: str) -> None:
        if self.decided:
            print("dispute already decided")
            return
        self.claimant_claim = claimant_claim
        self.respondent_claim = respondent_claim

    @gl.public.write
    def decide(self) -> None:
        if self.decided:
            print("already decided")
            return
        if not self.claimant_claim or not self.respondent_claim:
            print("both claims must be submitted first (call submit_claim)")
            return

        def leader_fn() -> str:
            prompt = (
                "You are a fair judge for a small on-chain dispute.\n"
                "Dispute: " + self.description + "\n"
                "CLAIMANT says: " + self.claimant_claim[:1500] + "\n"
                "RESPONDENT says: " + self.respondent_claim[:1500] + "\n"
                "Who should win based on the stronger, more consistent argument?\n"
                "Answer with exactly one word: CLAIMANT or RESPONDENT."
            )
            return gl.nondet.exec_prompt(prompt)

        def validator_fn(leader_result) -> bool:
            if not isinstance(leader_result, gl.vm.Return):
                return False
            text = str(leader_result.calldata).upper()
            return ("CLAIMANT" in text) or ("RESPONDENT" in text)

        res = gl.vm.run_nondet(leader_fn, validator_fn)
        raw = str(res) if not isinstance(res, gl.vm.Return) else str(res.calldata)

        if "CLAIMANT" in raw.upper():
            self.winner = "CLAIMANT"
        else:
            self.winner = "RESPONDENT"
        self.ruling_reason = raw[:500]
        self.decided = True

    @gl.public.view
    def get_ruling(self) -> dict:
        return {
            "description": self.description,
            "decided": self.decided,
            "winner": self.winner,
            "ruling_reason": self.ruling_reason,
        }
