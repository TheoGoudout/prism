import { Appearance } from "@/components/Common/Appearance"
import { Logo } from "@/components/Common/Logo"
import { AuthPreview } from "./AuthPreview"
import { Footer } from "./Footer"

interface AuthLayoutProps {
  children: React.ReactNode
}

export function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className="grid min-h-svh lg:grid-cols-2">
      <div className="relative hidden overflow-hidden bg-sidebar lg:flex lg:flex-col lg:items-center lg:justify-center">
        {/* Light split into its colours, falling across the panel */}
        <div
          aria-hidden="true"
          className="absolute -right-24 -top-24 size-[28rem] rounded-full bg-[radial-gradient(closest-side,oklch(0.62_0.2_350/0.45),transparent)] blur-2xl"
        />
        <div
          aria-hidden="true"
          className="absolute -bottom-32 -left-20 size-[32rem] rounded-full bg-[radial-gradient(closest-side,oklch(0.55_0.22_277/0.55),transparent)] blur-2xl"
        />
        <div
          aria-hidden="true"
          className="absolute bottom-1/4 right-10 size-64 rounded-full bg-[radial-gradient(closest-side,oklch(0.72_0.16_50/0.3),transparent)] blur-2xl"
        />
        <div className="relative flex flex-col items-center gap-10 text-center">
          <div className="flex flex-col items-center gap-5">
            <Logo
              variant="full"
              className="text-white [&_span]:text-4xl [&_svg]:size-12"
              asLink={false}
            />
            <p className="max-w-xs text-lg text-sidebar-foreground">
              Every platform, one clear picture.
            </p>
            <div
              aria-hidden="true"
              className="bg-spectrum h-1 w-24 rounded-full"
            />
          </div>
          <AuthPreview />
        </div>
      </div>
      <div className="flex flex-col gap-4 p-6 md:p-10">
        <div className="flex justify-end">
          <Appearance />
        </div>
        <div className="flex flex-1 items-center justify-center">
          <div className="w-full max-w-xs">{children}</div>
        </div>
        <Footer />
      </div>
    </div>
  )
}
