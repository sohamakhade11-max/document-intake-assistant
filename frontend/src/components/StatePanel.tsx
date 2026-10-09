import type { Conversation, FieldStatus } from "../types";

const STATUS_LABEL: Record<FieldStatus, string> = {
  unknown: "Unknown",
  confirmed: "Recorded",
  incomplete: "Incomplete",
  needs_clarification: "Needs your answer",
};

function Row({ label, status, children }: { label: string; status: FieldStatus; children: React.ReactNode }) {
  return (
    <div className={`row ${status}`}>
      <dt>{label}</dt>
      <dd>
        <span className="value">{children}</span>
        <span className={`tag ${status}`}>{STATUS_LABEL[status]}</span>
      </dd>
    </div>
  );
}

const unknown = <em>not provided</em>;
const yesNo = (v: boolean | null) => (v === null ? unknown : v ? "Yes" : "No");

export default function StatePanel({ conversation }: { conversation: Conversation }) {
  const { state: s, field_statuses: st, pending_conflicts } = conversation;
  return (
    <section className="panel" aria-label="Structured state">
      <h2>Structured state</h2>
      {pending_conflicts.length > 0 && (
        <p className="notice warn">Waiting for you to resolve: {pending_conflicts.map((c) => c.field).join(", ")}</p>
      )}
      <dl>
        <Row label="Full name" status={st["full_name"]}>{s.full_name ?? unknown}</Row>
        <Row label="Home address" status={st["home_address"]}>{s.home_address ?? unknown}</Row>
        <Row label="Covers worldwide assets" status={st["covers_worldwide_assets"]}>
          {yesNo(s.covers_worldwide_assets)}
        </Row>
        <Row label="Has children" status={st["has_children"]}>{yesNo(s.has_children)}</Row>
        {s.has_children !== false && (
          <Row label="Children" status={st["children"]}>
            {s.children.length ? s.children.join(", ") : unknown}
          </Row>
        )}
        <Row label="Executor" status={st["executor.name"]}>{s.executor.name ?? unknown}</Row>
        <Row label="Executor relationship" status={st["executor.relationship"]}>
          {s.executor.relationship ?? unknown}
        </Row>
        <Row label="Specific gifts" status={st["specific_gifts"]}>
          {s.specific_gifts === null ? (
            unknown
          ) : s.specific_gifts.length === 0 ? (
            "None"
          ) : (
            s.specific_gifts.map((g) => (g.recipient ? `${g.description} → ${g.recipient}` : g.description)).join("; ")
          )}
        </Row>
        <Row label="Additional wishes" status={st["additional_wishes"]}>
          {s.additional_wishes === null ? unknown : s.additional_wishes.length === 0 ? "None" : s.additional_wishes.join("; ")}
        </Row>
      </dl>
      <p className="progress">
        {conversation.is_complete
          ? "All required information collected."
          : `${conversation.missing_required.length} required item(s) still missing.`}
      </p>
    </section>
  );
}
