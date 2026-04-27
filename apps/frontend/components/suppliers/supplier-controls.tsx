"use client";

import { useState, useTransition } from "react";

import type { Supplier, SupplierPayload } from "@steelops/contracts";

export function SupplierCreateForm({ canManage }: { canManage: boolean }) {
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  if (!canManage) {
    return null;
  }

  function submit(formData: FormData) {
    setMessage(null);
    const payload = supplierPayloadFromForm(formData);
    startTransition(async () => {
      const response = await fetch("/api/suppliers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = (await response.json().catch(() => null)) as { detail?: string } | null;
      if (!response.ok) {
        setMessage(body?.detail ?? "Supplier could not be created.");
        return;
      }
      window.location.reload();
    });
  }

  return (
    <form action={submit} className="grid gap-3 rounded-2xl border bg-card p-4 md:grid-cols-4">
      <input name="name" required placeholder="Supplier name" className="rounded-xl border bg-background px-3 py-2 text-sm" disabled={isPending} />
      <input name="code" required placeholder="Code" className="rounded-xl border bg-background px-3 py-2 text-sm" disabled={isPending} />
      <input name="primary_port" placeholder="Primary port" className="rounded-xl border bg-background px-3 py-2 text-sm" disabled={isPending} />
      <button type="submit" disabled={isPending} className="rounded-2xl bg-primary px-4 py-2 text-sm font-semibold text-primaryForeground disabled:opacity-60">
        Add supplier
      </button>
      {message ? <p className="md:col-span-4 rounded-xl bg-muted px-3 py-2 text-sm">{message}</p> : null}
    </form>
  );
}

export function SupplierEditForm({
  supplier,
  canManage,
}: {
  supplier: Supplier;
  canManage: boolean;
}) {
  const [message, setMessage] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  if (!canManage) {
    return null;
  }

  function submit(formData: FormData) {
    setMessage(null);
    const payload = supplierPayloadFromForm(formData);
    startTransition(async () => {
      const response = await fetch(`/api/suppliers/${supplier.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = (await response.json().catch(() => null)) as { detail?: string } | null;
      if (!response.ok) {
        setMessage(body?.detail ?? "Supplier could not be updated.");
        return;
      }
      window.location.reload();
    });
  }

  return (
    <form action={submit} className="grid gap-3 md:grid-cols-2">
      <input name="name" defaultValue={supplier.name} required className="rounded-xl border bg-background px-3 py-2 text-sm" disabled={isPending} />
      <input name="code" defaultValue={supplier.code} required className="rounded-xl border bg-background px-3 py-2 text-sm" disabled={isPending} />
      <input name="primary_port" defaultValue={supplier.primary_port ?? ""} placeholder="Primary port" className="rounded-xl border bg-background px-3 py-2 text-sm" disabled={isPending} />
      <input name="country_of_origin" defaultValue={supplier.country_of_origin ?? ""} placeholder="Country" className="rounded-xl border bg-background px-3 py-2 text-sm" disabled={isPending} />
      <input name="contact_name" defaultValue={supplier.contact_name ?? ""} placeholder="Contact name" className="rounded-xl border bg-background px-3 py-2 text-sm" disabled={isPending} />
      <input name="contact_email" defaultValue={supplier.contact_email ?? ""} placeholder="Contact email" className="rounded-xl border bg-background px-3 py-2 text-sm" disabled={isPending} />
      <input name="secondary_ports" defaultValue={(supplier.secondary_ports ?? []).join(", ")} placeholder="Secondary ports, comma separated" className="rounded-xl border bg-background px-3 py-2 text-sm md:col-span-2" disabled={isPending} />
      <input name="material_categories" defaultValue={(supplier.material_categories ?? []).join(", ")} placeholder="Material categories, comma separated" className="rounded-xl border bg-background px-3 py-2 text-sm md:col-span-2" disabled={isPending} />
      <div className="flex flex-wrap gap-3 md:col-span-2">
        <button type="submit" disabled={isPending} className="rounded-2xl bg-primary px-4 py-2 text-sm font-semibold text-primaryForeground disabled:opacity-60">
          Save supplier
        </button>
        <SupplierLinkButton supplierId={supplier.id} />
        <SupplierDeleteButton supplierId={supplier.id} />
      </div>
      {message ? <p className="md:col-span-2 rounded-xl bg-muted px-3 py-2 text-sm">{message}</p> : null}
    </form>
  );
}

function SupplierLinkButton({ supplierId }: { supplierId: string }) {
  const [isPending, startTransition] = useTransition();

  return (
    <button
      type="button"
      disabled={isPending}
      onClick={() => {
        startTransition(async () => {
          await fetch(`/api/suppliers/${supplierId}/link-shipments`, { method: "POST" });
          window.location.reload();
        });
      }}
      className="rounded-2xl border px-4 py-2 text-sm font-semibold disabled:opacity-60"
    >
      Link matching shipments
    </button>
  );
}

function SupplierDeleteButton({ supplierId }: { supplierId: string }) {
  const [isPending, startTransition] = useTransition();

  return (
    <button
      type="button"
      disabled={isPending}
      onClick={() => {
        startTransition(async () => {
          await fetch(`/api/suppliers/${supplierId}`, { method: "DELETE" });
          window.location.href = "/dashboard/suppliers";
        });
      }}
      className="rounded-2xl border border-accent px-4 py-2 text-sm font-semibold text-primary disabled:opacity-60"
    >
      Deactivate
    </button>
  );
}

function supplierPayloadFromForm(formData: FormData): SupplierPayload {
  return {
    name: String(formData.get("name") ?? "").trim(),
    code: String(formData.get("code") ?? "").trim(),
    primary_port: emptyToNull(formData.get("primary_port")),
    country_of_origin: emptyToNull(formData.get("country_of_origin")),
    contact_name: emptyToNull(formData.get("contact_name")),
    contact_email: emptyToNull(formData.get("contact_email")),
    secondary_ports: listValue(formData.get("secondary_ports")),
    material_categories: listValue(formData.get("material_categories")),
    is_active: true,
  };
}

function emptyToNull(value: FormDataEntryValue | null) {
  const text = String(value ?? "").trim();
  return text || null;
}

function listValue(value: FormDataEntryValue | null) {
  const items = String(value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return items.length > 0 ? items : null;
}
