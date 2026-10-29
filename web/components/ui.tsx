import Link from "next/link";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

const base =
  "inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed";
const variants = {
  primary: "bg-lamp text-night hover:bg-lampdeep",
  quiet: "border border-line text-paper hover:border-dusk",
  danger: "border border-ember/60 text-ember hover:bg-ember/10",
} as const;

export function Button({ variant = "primary", className = "", ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: keyof typeof variants }) {
  return <button className={`${base} ${variants[variant]} ${className}`} {...rest} />;
}

export function LinkButton({ href, variant = "primary", children, className = "" }: { href: string; variant?: keyof typeof variants; children: ReactNode; className?: string }) {
  return (
    <Link href={href} className={`${base} ${variants[variant]} ${className}`}>
      {children}
    </Link>
  );
}

export function Field({ label, hint, children, htmlFor }: { label: string; hint?: ReactNode; children: ReactNode; htmlFor?: string }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="block text-sm font-medium text-paper">
        {label}
      </label>
      {children}
      {hint ? <p className="text-xs text-mute">{hint}</p> : null}
    </div>
  );
}

const inputCls =
  "w-full rounded-md border border-line bg-night px-3 py-2 text-sm text-paper placeholder:text-mute/60 focus:border-lamp focus:outline-none";

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${inputCls} ${props.className || ""}`} />;
}
export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={`${inputCls} ${props.className || ""}`} />;
}
export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`${inputCls} ${props.className || ""}`} />;
}

export function PageHead({ title, sub, action }: { title: string; sub?: ReactNode; action?: ReactNode }) {
  return (
    <header className="mb-8 flex flex-wrap items-end justify-between gap-4 border-b border-line pb-5">
      <div className="max-w-2xl">
        <h1 className="text-4xl">{title}</h1>
        {sub ? <p className="mt-1 text-mute">{sub}</p> : null}
      </div>
      {action}
    </header>
  );
}

export function StatusPill({ status }: { status: string }) {
  const map: Record<string, string> = {
    queued: "text-dusk border-dusk/40",
    processing: "text-lamp border-lamp/50",
    training: "text-lamp border-lamp/50",
    completed: "text-sage border-sage/40",
    ready: "text-sage border-sage/40",
    failed: "text-ember border-ember/50",
    cancelled: "text-mute border-line",
  };
  const label: Record<string, string> = { processing: "Working", training: "Learning", completed: "Done" };
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs ${map[status] || "text-mute border-line"}`}>
      {label[status] || status[0].toUpperCase() + status.slice(1)}
    </span>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "error"; children: ReactNode }) {
  return (
    <div role={tone === "error" ? "alert" : "status"} className={`rounded-md border px-4 py-3 text-sm ${tone === "error" ? "border-ember/50 text-ember" : "border-line text-mute"}`}>
      {children}
    </div>
  );
}

export function Empty({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-line px-6 py-12">
      <h2 className="text-2xl">{title}</h2>
      <p className="mt-1 max-w-md text-mute">{body}</p>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}
