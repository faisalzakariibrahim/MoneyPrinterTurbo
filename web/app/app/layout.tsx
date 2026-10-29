import { redirect } from "next/navigation";
import { NavRail } from "@/components/NavRail";
import { requireUser } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export default async function StudioLayout({ children }: { children: React.ReactNode }) {
  const { user } = await requireUser();
  if (!user) redirect("/login");
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-4 md:flex-row md:gap-10 md:px-8 md:py-0">
      <NavRail email={user.email || ""} />
      <main className="min-w-0 flex-1 pb-24 md:py-10">{children}</main>
    </div>
  );
}
