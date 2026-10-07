/**
 * Demonstration wire for the landing page. Everything here is an example:
 * an invented client and invented trend copy, labelled as such on the page.
 */

export const EXAMPLE_CLIENT = {
  name: "Harbor & Pine",
  initials: "HP",
  what: "a B2B cybersecurity consultancy",
  services: [
    "Compliance advisory",
    "Incident response",
    "Security awareness training",
  ],
  threshold: 60,
};

export type Priority = "FLASH" | "URGENT" | "ROUTINE";

export type WireItem = {
  id: string;
  source: string;
  time: string;
  headline: string;
  fit: number;
  /** Which of the client's services the trend matched. */
  matched?: string[];
  /** The post the desk sets for items that fit. */
  post?: string;
  hashtags?: string;
};

export const WIRE: WireItem[] = [
  {
    id: "eu-ai-reporting",
    source: "Google News",
    time: "09:42",
    headline:
      "EU publishes draft guidance on AI incident reporting for small firms",
    fit: 91,
    matched: ["Compliance advisory", "Incident response"],
    post: "The EU's draft guidance on AI incident reporting landed this morning, and small firms are in scope.\n\nThree things to check this week:\n1. Do you know which of your tools use AI?\n2. Who decides whether an incident is reportable?\n3. Can you produce a timeline within 72 hours?\n\nIf any answer is \"not sure\", that's where we'd start.",
    hashtags: "#Compliance #AIAct #IncidentResponse",
  },
  {
    id: "pumpkin-spice",
    source: "Google Trends",
    time: "09:39",
    headline: "Pumpkin spice searches peak a week earlier than last year",
    fit: 4,
  },
  {
    id: "cyber-cover",
    source: "RSS · Insurance Times",
    time: "09:35",
    headline: "Mid-size insurers tighten cyber cover terms for 2027 renewals",
    fit: 84,
    matched: ["Compliance advisory"],
    post: "Cyber insurance renewals for 2027 are coming with tighter terms.\n\nInsurers are asking for proof, not promises: MFA everywhere, tested backups, a written incident plan.\n\nOur renewal checklist maps each question to the evidence an underwriter expects. Ask us for a copy.",
    hashtags: "#CyberInsurance #RiskManagement",
  },
  {
    id: "goalkeeper",
    source: "Google News",
    time: "09:31",
    headline: "Record transfer fee paid for a goalkeeper",
    fit: 2,
  },
  {
    id: "cloud-permissions",
    source: "Hacker News",
    time: "09:26",
    headline:
      "Show HN: an open-source tool that maps cloud permissions in minutes",
    fit: 78,
    matched: ["Incident response"],
    post: "During an incident, the first question is always \"what could this account reach?\"\n\nA new open-source tool on Hacker News maps cloud permissions in minutes. We tried it on a test tenant: useful for a first pass, not a substitute for reviewing who should have access.\n\nWe'll share our notes on where it helps and where it doesn't.",
    hashtags: "#CloudSecurity #IncidentResponse",
  },
  {
    id: "bare-metal",
    source: "Hacker News",
    time: "09:20",
    headline: "Why we moved our CI back to bare metal",
    fit: 31,
  },
  {
    id: "parcel-phishing",
    source: "Google Trends",
    time: "09:14",
    headline:
      "Phishing texts impersonating parcel firms surge before the holidays",
    fit: 72,
    matched: ["Security awareness training"],
    post: "Parcel-delivery phishing texts always rise before the holidays, and searches for them are climbing now.\n\nA two-minute refresher for your team:\n• Real couriers don't ask for card details by text.\n• Check the tracking number on the courier's own site.\n• Report it, then delete it.\n\nForward this to whoever runs your team chat.",
    hashtags: "#SecurityAwareness #Phishing",
  },
  {
    id: "linkedin-video",
    source: "Reddit · r/marketing",
    time: "09:08",
    headline: "LinkedIn tests longer videos in the main feed",
    fit: 22,
  },
  {
    id: "password-managers",
    source: "Reddit · r/sysadmin",
    time: "09:01",
    headline:
      "Which password managers are teams actually rolling out this year?",
    fit: 64,
    matched: ["Security awareness training"],
    post: '"Which password manager should we use?" is the wrong first question.\n\nThe right one: how will people actually use it on day one? Rollouts fail on habits, not features.\n\nWe help teams pick, roll out and train in the same month.',
    hashtags: "#PasswordSecurity #SecurityAwareness",
  },
];

export function priorityOf(item: WireItem): Priority {
  if (item.fit >= 90) return "FLASH";
  if (item.fit >= EXAMPLE_CLIENT.threshold) return "URGENT";
  return "ROUTINE";
}

export const FITTING = WIRE.filter((i) => i.fit >= EXAMPLE_CLIENT.threshold);
