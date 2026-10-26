import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Api } from "../src/api/client";
import { Detail } from "../src/features/Detail";
import { detail } from "./fixtures";
import { t } from "../src/app/i18n";

describe("separate review and actual payload evidence", () => {
  it("shows factual and editorial findings without inferring approval from facts", async () => {
    const source = structuredClone(detail);
    source.selection!.assessment.editorial_status = "revise";
    source.selection!.assessment.factual_pass = true;
    source.selection!.review = { id: "review-fictional", findings: "Verified fictional source attribution.", tone_findings: "Direct language.", limitations: "Synthetic fixture only.", editorial: { argument: "A documented handover can help this operations owner.", decision: "revise", findings: "The request is unclear and needs revision.", binding: "a".repeat(64) } };
    const api = new Api();
    const command = vi.spyOn(api, "command");
    render(<Detail detail={source} api={api} onDirty={vi.fn()} refresh={vi.fn()} onPacket={vi.fn()} />);
    await userEvent.setup().click(screen.getByRole("button", { name: t("review.findings") }));
    expect(await screen.findByText("Verified fictional source attribution.")).toBeVisible();
    expect(screen.getByText(source.selection!.review.editorial!.argument)).toBeVisible();
    expect(screen.getByText(t("editorial.revise"))).toBeVisible();
    expect(command).not.toHaveBeenCalled();
  });
  it("retains actual sent evidence and exposes observed/pinned mismatch hashes", async () => {
    const source = structuredClone(detail);
    source.history = [{ id: "observed-fictional", kind: "sent", occurred_at: "2026-10-26T00:00:00Z", evidence: "Synthetic observed provider receipt.", packet_id: "packet-aurora", version_id: "version-old", message_sha256: "b".repeat(64), pinned_message_sha256: "c".repeat(64), warnings: [{ code: "SENT_PAYLOAD_MISMATCH", message: "Observed mismatch retained." }] }];
    render(<Detail detail={source} api={new Api()} onDirty={vi.fn()} refresh={vi.fn()} onPacket={vi.fn()} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: t("detail.history") }));
    expect(screen.getByText("Synthetic observed provider receipt.")).toBeVisible();
    expect(screen.getByText(t("issue.SENT_PAYLOAD_MISMATCH"))).toBeVisible();
    await user.click(screen.getByRole("button", { name: t("history.payloadEvidence") }));
    expect(screen.getByText("b".repeat(64))).toBeVisible();
    expect(screen.getByText("c".repeat(64))).toBeVisible();
  });
});
