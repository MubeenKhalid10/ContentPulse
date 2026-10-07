"use client";

import { ArrowLeftIcon, ArrowRightIcon } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { WORKFLOW } from "@/lib/workflow";
import type { Me } from "@/types/api";

const SEEN_KEY = "cp_welcome_seen_v1";
const REPLAY_EVENT = "cp:welcome";

function seen(): boolean {
  try {
    return window.localStorage.getItem(SEEN_KEY) === "1";
  } catch {
    return true; // storage blocked: don't nag on every visit
  }
}

function markSeen() {
  try {
    window.localStorage.setItem(SEEN_KEY, "1");
  } catch {
    // Storage unavailable; the tour may show again next time.
  }
}

/** Open the tour again (account menu → "Show the welcome tour"). */
export function replayWelcomeTour() {
  window.dispatchEvent(new Event(REPLAY_EVENT));
}

/**
 * Three short screens explaining the product once, on the first dashboard
 * visit. Skippable at every step; never shown again after it's closed.
 */
export function WelcomeTour({ me }: { me: Me }) {
  const pathname = usePathname();
  // The shell renders only in the browser (after /auth/me), so storage is readable here.
  const [firstVisit] = useState(() => !seen());
  const [dismissed, setDismissed] = useState(false);
  const [replaying, setReplaying] = useState(false);
  const [step, setStep] = useState(0);
  const isAdmin = me.permissions.includes("organization.write");
  const steps = WORKFLOW.filter((s) => me.permissions.includes(s.permission));
  // First visit: only on the dashboard, so a deep link into a task isn't interrupted.
  const open = replaying || (firstVisit && !dismissed && pathname === "/dashboard");

  useEffect(() => {
    const replay = () => {
      setStep(0);
      setReplaying(true);
    };
    window.addEventListener(REPLAY_EVENT, replay);
    return () => window.removeEventListener(REPLAY_EVENT, replay);
  }, []);

  const close = () => {
    markSeen();
    setDismissed(true);
    setReplaying(false);
  };

  const screens = [
    {
      title: "Welcome to ContentPulse",
      description:
        "ContentPulse finds trends that matter to your organization and helps your team turn them into approved social posts.",
      body: (
        <ol className="grid gap-2" aria-label="The workflow">
          {steps.map((s) => (
            <li key={s.href} className="flex items-start gap-3 text-sm">
              <span
                aria-hidden
                className="mt-px grid size-5 shrink-0 place-items-center rounded-full bg-muted text-[11px] font-semibold tabular-nums text-muted-foreground"
              >
                {s.n}
              </span>
              <span>
                <span className="font-medium">{s.label}</span>
                <span className="text-muted-foreground"> · {s.summary}</span>
              </span>
            </li>
          ))}
        </ol>
      ),
    },
    {
      title: "It works from what you tell it",
      description: isAdmin
        ? "Your services, audience and brand voice decide which trends count as relevant and how posts sound. Setting this up takes about 10 minutes, and the dashboard walks you through it."
        : "Your admin describes the organization: its services, audience and brand voice. ContentPulse uses that to pick relevant trends and to write posts that sound like you.",
      body: (
        <ul className="grid gap-1.5 text-sm text-muted-foreground">
          <li>• Trends unrelated to what you do are marked “Not relevant”.</li>
          <li>• Posts only make claims your website and documents back up.</li>
          <li>• Nothing is published: every post is reviewed and approved by a person.</li>
        </ul>
      ),
    },
    {
      title: "Follow the numbered steps",
      description:
        "The sidebar lists the steps in order, and the dashboard always shows your next step, so you don't have to guess where to go.",
      body: (
        <ul className="grid gap-1.5 text-sm text-muted-foreground">
          <li>• Creators shortlist topics, write each post, add its design and send it for approval.</li>
          <li>• Admins approve posts in Approvals, which makes them ready to publish.</li>
          <li>• Viewers can see everything and share finished posts.</li>
        </ul>
      ),
    },
  ];
  const screen = screens[step];
  const last = step === screens.length - 1;

  return (
    <Dialog open={open} onOpenChange={(next) => !next && close()}>
      <DialogContent className="sm:max-w-md" aria-describedby="welcome-description">
        <DialogHeader>
          <DialogTitle>{screen.title}</DialogTitle>
          <DialogDescription id="welcome-description">{screen.description}</DialogDescription>
        </DialogHeader>
        <div className="min-h-36">{screen.body}</div>
        <DialogFooter className="items-center sm:justify-between">
          <div className="flex items-center gap-1.5" aria-label={`Step ${step + 1} of ${screens.length}`} role="img">
            {screens.map((_, i) => (
              <span
                key={i}
                className={cn(
                  "h-1.5 rounded-full transition-all duration-200",
                  i === step ? "w-4 bg-foreground" : "w-1.5 bg-muted-foreground/30",
                )}
              />
            ))}
          </div>
          <div className="flex gap-2">
            {step === 0 ? (
              <Button variant="ghost" onClick={close}>
                Skip tour
              </Button>
            ) : (
              <Button variant="ghost" onClick={() => setStep(step - 1)}>
                <ArrowLeftIcon />
                Back
              </Button>
            )}
            {last ? (
              <Button onClick={close}>Get started</Button>
            ) : (
              <Button onClick={() => setStep(step + 1)}>
                Next
                <ArrowRightIcon />
              </Button>
            )}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
