import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Role } from "../api";
import { useAuth } from "../auth";
import { MOBILE, useMediaQuery } from "../hooks";
import { Alert, Badge, Button, Card, CopyLink, Field, Input, Select, useAsync } from "../components/ui";

interface Member {
  user_id: number;
  name: string;
  email: string;
  role: Role;
  joined_at: string;
  is_you: boolean;
}
interface Invite {
  id: number;
  email: string;
  role: Role;
  status: "pending" | "expired";
  expires_at: string;
  invited_by: string | null;
  link: string | null;
}

const RANK: Record<Role, number> = { member: 1, admin: 2, owner: 3 };

export default function MembersPage() {
  const { company, refresh } = useAuth();
  const navigate = useNavigate();
  const [members, setMembers] = useState<Member[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("member");
  const [lastLink, setLastLink] = useState<{ email: string; link: string } | null>(null);
  const { busy, error, setError, run } = useAsync();
  const mobile = useMediaQuery(MOBILE);
  const myRole = company?.role ?? "member";
  const canAdmin = RANK[myRole] >= RANK.admin;

  const load = useCallback(async () => {
    setMembers(await api<Member[]>("/company/members"));
    if (canAdmin) setInvites(await api<Invite[]>("/company/invites"));
  }, [canAdmin]);

  useEffect(() => {
    if (company) load().catch((e: Error) => setError(e.message));
  }, [company, load, setError]);

  const roleOptions: Role[] = (["member", "admin", "owner"] as Role[]).filter((r) => RANK[r] <= RANK[myRole]);

  return (
    <>
      <div className="page-head">
        <h1>Members</h1>
      </div>
      {error && <Alert kind="error">{error}</Alert>}

      {canAdmin && (
        <Card title="Invite someone">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void run(async () => {
                const inv = await api<Invite>("/company/invites", { body: { email, role } });
                setLastLink(inv.link ? { email: inv.email, link: inv.link } : null);
                setEmail("");
                await load();
              });
            }}
          >
            <div className="row" style={{ alignItems: "flex-end" }}>
              <div style={{ flex: "2 1 240px" }}>
                <Field label="Email" htmlFor="invite-email">
                  <Input id="invite-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
                </Field>
              </div>
              <div style={{ flex: "1 1 140px" }}>
                <Field label="Role" htmlFor="invite-role">
                  <Select id="invite-role" value={role} onChange={(e) => setRole(e.target.value as Role)}>
                    {roleOptions.map((r) => (
                      <option key={r} value={r}>
                        {r[0].toUpperCase() + r.slice(1)}
                      </option>
                    ))}
                  </Select>
                </Field>
              </div>
              <div className="field">
                <Button variant="primary" disabled={busy}>
                  Invite
                </Button>
              </div>
            </div>
          </form>
          {lastLink && (
            <>
              <p className="small" style={{ marginBottom: 6 }}>
                Invitation link for <strong>{lastLink.email}</strong> — copy it and send it yourself if they don't get the
                email:
              </p>
              <CopyLink link={lastLink.link} />
            </>
          )}
          <p className="small muted" style={{ marginTop: 12, marginBottom: 0 }}>
            Members can use the app. Admins can also invite people and edit company settings. Owners can do everything,
            including managing other owners.
          </p>
        </Card>
      )}

      <Card title={`People (${members.length})`}>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                {!mobile && <th>Email</th>}
                <th>Role</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {members.map((m) => {
                const canEdit = canAdmin && !m.is_you && (myRole === "owner" || m.role === "member");
                return (
                  <tr key={m.user_id}>
                    <td>
                      {m.name || "—"} {m.is_you && <span className="muted small">(you)</span>}
                      {mobile && <div className="muted small">{m.email}</div>}
                    </td>
                    {!mobile && <td>{m.email}</td>}
                    <td>
                      {canEdit ? (
                        <Select
                          value={m.role}
                          aria-label={`Role for ${m.email}`}
                          style={{ maxWidth: 140 }}
                          onChange={(e) =>
                            run(async () => {
                              await api(`/company/members/${m.user_id}`, { method: "PUT", body: { role: e.target.value } });
                              await load();
                            })
                          }
                        >
                          {roleOptions.map((r) => (
                            <option key={r} value={r}>
                              {r[0].toUpperCase() + r.slice(1)}
                            </option>
                          ))}
                        </Select>
                      ) : (
                        <Badge tone={m.role}>{m.role}</Badge>
                      )}
                    </td>
                    <td className="num">
                      {m.is_you ? (
                        <Button
                          size="sm"
                          variant="danger"
                          onClick={() =>
                            confirm(`Leave ${company?.name}?`) &&
                            run(async () => {
                              await api(`/company/members/${m.user_id}`, { method: "DELETE" });
                              await refresh();
                              navigate("/");
                            })
                          }
                        >
                          Leave
                        </Button>
                      ) : (
                        canEdit && (
                          <Button
                            size="sm"
                            variant="danger"
                            onClick={() =>
                              confirm(`Remove ${m.email} from ${company?.name}?`) &&
                              run(async () => {
                                await api(`/company/members/${m.user_id}`, { method: "DELETE" });
                                await load();
                              })
                            }
                          >
                            Remove
                          </Button>
                        )
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {canAdmin && invites.length > 0 && (
        <Card title="Pending invitations">
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Expires</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {invites.map((i) => (
                  <tr key={i.id}>
                    <td>{i.email}</td>
                    <td>
                      <Badge tone={i.role}>{i.role}</Badge>
                    </td>
                    <td>
                      <Badge tone={i.status}>{i.status}</Badge>
                    </td>
                    <td className="small">{new Date(i.expires_at).toLocaleDateString()}</td>
                    <td className="num">
                      <div className="row" style={{ justifyContent: "flex-end" }}>
                        <Button
                          size="sm"
                          onClick={() =>
                            run(async () => {
                              const inv = await api<Invite>(`/company/invites/${i.id}/renew`, { method: "POST" });
                              if (inv.link) setLastLink({ email: inv.email, link: inv.link });
                              await load();
                            })
                          }
                        >
                          New link
                        </Button>
                        <Button
                          size="sm"
                          variant="danger"
                          onClick={() =>
                            run(async () => {
                              await api(`/company/invites/${i.id}`, { method: "DELETE" });
                              await load();
                            })
                          }
                        >
                          Revoke
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="small muted" style={{ marginTop: 12, marginBottom: 0 }}>
            For security, links are only shown when created. Use “New link” to get a fresh one (the old link stops
            working).
          </p>
        </Card>
      )}
    </>
  );
}
