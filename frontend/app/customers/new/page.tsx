"use client";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { api, Json, post } from "@/lib/api";
import { Card, ErrorBox, Field, Spinner } from "@/components/ui";

const EMPTY = {
  full_name: "", date_of_birth: "", nationality: "", country_of_residence: "", address: "", occupation: "", industry: "",
  source_of_funds: "", source_of_wealth: "", expected_activity: "", annual_income: "", product: "CURRENT_ACCOUNT", channel: "FACE_TO_FACE", pep_declared: false,
};

const EXAMPLE = {
  full_name: "Hassan Al-Rashidi", date_of_birth: "1975-11-02", nationality: "Iran", country_of_residence: "United Arab Emirates",
  address: "Marina Walk, Dubai", occupation: "Trader", industry: "Import/export trading",
  source_of_funds: "Trading profits.", source_of_wealth: "Family business.",
  expected_activity: "Incoming wires of EUR 100,000 per month", annual_income: "60000", product: "INTERNATIONAL_WIRES", channel: "INTERMEDIARY", pep_declared: false,
};

export default function NewCustomer() {
  const router = useRouter();
  const [f, setF] = useState<Json>(EMPTY);
  const [meta, setMeta] = useState<Json>({ products: ["CURRENT_ACCOUNT"], channels: ["FACE_TO_FACE"] });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => { api("/meta").then(setMeta).catch(() => undefined); }, []);
  const set = (k: string) => (e: Json) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const body = { ...f, annual_income: f.annual_income === "" ? null : Number(f.annual_income) };
      for (const k of ["address", "source_of_funds", "source_of_wealth", "expected_activity"]) if (!body[k]) body[k] = null;
      const res = await post("/customers?assess=true", body);
      router.push(`/customers/${res.customer.id}`);
    } catch (ex) {
      setErr((ex as Error).message);
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto max-w-4xl space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Customer intake</h1>
        <button type="button" className="btn-secondary" onClick={() => setF(EXAMPLE)}>Load risky example</button>
      </div>
      <Card title="Identity">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Full name *"><input required className="input" value={f.full_name} onChange={set("full_name")} /></Field>
          <Field label="Date of birth *"><input required type="date" className="input" value={f.date_of_birth} onChange={set("date_of_birth")} /></Field>
          <Field label="Nationality *"><input required className="input" value={f.nationality} onChange={set("nationality")} placeholder="e.g. Poland" /></Field>
          <Field label="Country of residence *"><input required className="input" value={f.country_of_residence} onChange={set("country_of_residence")} /></Field>
          <div className="sm:col-span-2"><Field label="Residential address"><input className="input" value={f.address} onChange={set("address")} /></Field></div>
        </div>
      </Card>
      <Card title="Occupation & relationship">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Occupation *"><input required className="input" value={f.occupation} onChange={set("occupation")} /></Field>
          <Field label="Industry *"><input required className="input" value={f.industry} onChange={set("industry")} placeholder="e.g. Information technology" /></Field>
          <Field label="Annual income (EUR)"><input type="number" min="0" className="input" value={f.annual_income} onChange={set("annual_income")} /></Field>
          <Field label="Product"><select className="input" value={f.product} onChange={set("product")}>{meta.products.map((p: string) => <option key={p}>{p}</option>)}</select></Field>
          <Field label="Channel"><select className="input" value={f.channel} onChange={set("channel")}>{meta.channels.map((p: string) => <option key={p}>{p}</option>)}</select></Field>
          <label className="flex items-center gap-2 pt-6 text-sm"><input type="checkbox" checked={f.pep_declared} onChange={set("pep_declared")} /> Customer declares they are a PEP</label>
        </div>
      </Card>
      <Card title="Funds & wealth">
        <div className="space-y-4">
          <Field label="Source of funds" hint="Where will the money flowing through the account come from?"><textarea rows={2} className="input" value={f.source_of_funds} onChange={set("source_of_funds")} /></Field>
          <Field label="Source of wealth" hint="How was the customer's overall wealth accumulated?"><textarea rows={3} className="input" value={f.source_of_wealth} onChange={set("source_of_wealth")} /></Field>
          <Field label="Expected activity" hint="e.g. 'Salary credits of EUR 4,000 per month'"><textarea rows={2} className="input" value={f.expected_activity} onChange={set("expected_activity")} /></Field>
        </div>
      </Card>
      <ErrorBox message={err} />
      <div className="flex items-center gap-4">
        <button className="btn" disabled={busy}>Create customer & run AML agents</button>
        {busy && <Spinner label="Running KYC, screening, CDD, EDD, SoF, SoW, risk and case summary agents..." />}
      </div>
    </form>
  );
}
