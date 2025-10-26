import { motion } from "framer-motion";
import { Navbar } from "@/components/core/Navbar";
import { FallDetector } from "@/features/fall-detector/FallDetector";
import { fadeIn } from "@/styles/motion";

export function DashboardPage() {

  return (
    <div className="min-h-screen bg-bg text-ink">
      <Navbar />
      <main className="container space-y-6 py-8">
        <motion.section {...fadeIn}>
          <div className="space-y-3">
            <h1 className="text-3xl font-semibold leading-tight">Fall Motion Detector</h1>
            <p className="text-sm text-ink-muted">Focused readouts that surface motion shifts without shouting.</p>
          </div>
        </motion.section>
        <motion.section {...fadeIn}>
          <FallDetector />
        </motion.section>
      </main>
    </div>
  );
}
