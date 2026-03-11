import { NavBar } from "@/components/nav-bar";

export default function AuthenticatedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen">
      <NavBar />
      <main className="mx-auto max-w-7xl px-4 py-6 animate-fade-in">
        {children}
      </main>
    </div>
  );
}
