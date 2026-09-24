"""Cost forecast for the build.

Two halves to any forecast: how much the system consumes, and what that costs.
This file knows the first half exactly — the prompt sizes are measured from the
real prompts in packages/agents and apps/host/summarize.py, not guessed — and
knows nothing about the second until you fill in the rates from the Nebius
pricing page.

    python scripts/forecast.py --help
    python scripts/forecast.py --nano-in 0.04 --nano-out 0.12 \
                               --super-in 0.30 --super-out 0.90 \
                               --ultra-in 1.00 --ultra-out 3.00 \
                               --vm-hourly 1.50 --vm-hours-per-day 8

Rates are USD per million tokens. Every number printed is a consequence of
arguments you supplied; nothing is assumed about price.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

# Measured from the shipped prompts. Roughly 4 characters per token, which is
# the usual rule of thumb for English and is good to about ±20%.
SUMMARIZE_PROMPT_TOKENS = 400        # 130 system + ~265 for a 20-line batch
SUMMARIZE_OUTPUT_TOKENS = 250        # 20 short lines back

AGENT_SYSTEM_TOKENS = 950            # guardrails + master + adaptation + tools
AGENT_AVG_PROMPT_TOKENS = 1800       # grows with history over a 4-call run
AGENT_OUTPUT_TOKENS = 200
CALLS_PER_AGENT_RUN = 4

GROUNDING_PROMPT_TOKENS = 800        # claim + search results + judge prompt
GROUNDING_OUTPUT_TOKENS = 20         # one word
CLAIMS_PER_NIGHT = 3                 # rows with an external_claim in the seed data


@dataclass
class Rate:
    name: str
    input_per_mtok: float | None
    output_per_mtok: float | None

    def cost(self, prompt: float, completion: float) -> float | None:
        if self.input_per_mtok is None or self.output_per_mtok is None:
            return None
        return prompt / 1e6 * self.input_per_mtok + completion / 1e6 * self.output_per_mtok


def money(value: float | None) -> str:
    return "  (rate unknown)" if value is None else f"${value:,.2f}"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--nano-in", type=float), p.add_argument("--nano-out", type=float)
    p.add_argument("--super-in", type=float), p.add_argument("--super-out", type=float)
    p.add_argument("--ultra-in", type=float), p.add_argument("--ultra-out", type=float)
    p.add_argument("--vm-hourly", type=float, help="GPU VM USD per hour")
    p.add_argument("--vm-hours-per-day", type=float, default=8.0,
                   help="Hours the VM is actually up. Default 8 — stop it overnight.")
    p.add_argument("--days", type=int, default=36, help="Days to the deadline. Default 36 (24 Sep to 30 Oct).")
    p.add_argument("--agent-runs-per-day", type=int, default=40,
                   help="Agent runs while developing and demoing.")
    p.add_argument("--summarize-batches-per-day", type=int, default=400,
                   help="One batch per ~2s of agent activity. 400 is roughly 15 active minutes a day.")
    args = p.parse_args()

    nano = Rate("Nano", args.nano_in, args.nano_out)
    super_ = Rate("Super", args.super_in, args.super_out)
    ultra = Rate("Ultra", args.ultra_in, args.ultra_out)

    # Per day
    sum_prompt = args.summarize_batches_per_day * SUMMARIZE_PROMPT_TOKENS
    sum_out = args.summarize_batches_per_day * SUMMARIZE_OUTPUT_TOKENS

    agent_calls = args.agent_runs_per_day * CALLS_PER_AGENT_RUN
    agent_prompt = agent_calls * AGENT_AVG_PROMPT_TOKENS
    agent_out = agent_calls * AGENT_OUTPUT_TOKENS

    ground_prompt = CLAIMS_PER_NIGHT * GROUNDING_PROMPT_TOKENS
    ground_out = CLAIMS_PER_NIGHT * GROUNDING_OUTPUT_TOKENS

    rows = [
        ("Nano   · activity feed", nano, sum_prompt, sum_out),
        ("Super  · agent execution", super_, agent_prompt, agent_out),
        ("Ultra  · nightly grounding", ultra, ground_prompt, ground_out),
    ]

    print(f"\nForecast over {args.days} days\n" + "=" * 62)
    print(f"{'':28}{'tokens/day':>14}{'per day':>10}{'total':>10}")

    total = 0.0
    unknown = False
    for label, rate, prompt, out in rows:
        daily = rate.cost(prompt, out)
        if daily is None:
            unknown = True
            print(f"{label:28}{prompt + out:>14,}{'—':>10}{'—':>10}")
        else:
            total += daily * args.days
            print(f"{label:28}{prompt + out:>14,}{money(daily):>10}{money(daily * args.days):>10}")

    print("-" * 62)
    if args.vm_hourly is not None:
        vm = args.vm_hourly * args.vm_hours_per_day * args.days
        total += vm
        print(f"{'GPU VM':28}{f'{args.vm_hours_per_day:g} h/day':>14}"
              f"{money(args.vm_hourly * args.vm_hours_per_day):>10}{money(vm):>10}")
        idle = args.vm_hourly * 24 * args.days
        print(f"{'  if left running 24/7':28}{'':>14}{'':>10}{money(idle):>10}")
    else:
        unknown = True
        print(f"{'GPU VM':28}{'—':>14}{'—':>10}{'—':>10}   pass --vm-hourly")

    print("=" * 62)
    print(f"{'TOTAL (of what is priced)':28}{'':>14}{'':>10}{money(total):>10}")
    if unknown:
        print("\nSome rates were not supplied, so this total is partial.")
    print("\nInference is almost certainly the small half. The VM dominates,")
    print("and hours-per-day is the one number you control most cheaply.\n")


if __name__ == "__main__":
    main()
