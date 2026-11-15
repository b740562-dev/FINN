/** Text for the spoken brief. Browser voices read raw figures badly (an Indian
 *  voice may read "60.7 lakh" as one long number), so every figure is written
 *  out in words the Indian way: "sixty point seven lakh rupees", "fifty point
 *  five crore rupees", "fifty thousand rupees", "five hundred rupees". */

const ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
  "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"];
const TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"];

function under100(n: number): string {
  if (n < 20) return ONES[n];
  return TENS[Math.floor(n / 10)] + (n % 10 ? " " + ONES[n % 10] : "");
}

/** Whole number in Indian words: 6070000 -> "sixty lakh seventy thousand". */
export function intWords(n: number): string {
  n = Math.floor(Math.abs(n));
  if (n === 0) return "zero";
  const parts: string[] = [];
  const crore = Math.floor(n / 1e7);
  const lakh = Math.floor((n % 1e7) / 1e5);
  const thousand = Math.floor((n % 1e5) / 1e3);
  const hundred = Math.floor((n % 1e3) / 100);
  const rest = n % 100;
  if (crore) parts.push(intWords(crore) + " crore");
  if (lakh) parts.push(under100(lakh) + " lakh");
  if (thousand) parts.push(under100(thousand) + " thousand");
  if (hundred) parts.push(ONES[hundred] + " hundred");
  if (rest) parts.push(under100(rest));
  return parts.join(" ");
}

/** Any number in words, decimals read digit by digit: 60.7 -> "sixty point seven". */
export function numberWords(x: number, maxDecimals = 2): string {
  const neg = x < 0;
  const s = Math.abs(x).toFixed(maxDecimals).replace(/\.?0+$/, "");
  const [whole, frac] = s.split(".");
  const w = intWords(Number(whole)) + (frac ? " point " + frac.split("").map((d) => ONES[Number(d)]).join(" ") : "");
  return (neg ? "minus " : "") + w;
}

/** A rupee amount, the way an Indian investor says it. */
export function rupeesWords(amount: number): string {
  const a = Math.abs(amount);
  const unit = (v: number, name: string) => `${numberWords(v >= 100 ? Math.round(v) : Math.round(v * 10) / 10, 1)} ${name} rupees`;
  if (a >= 1e7) return unit(a / 1e7, "crore");
  if (a >= 1e5) return unit(a / 1e5, "lakh");
  if (a < 1000 && !Number.isInteger(a)) return `${numberWords(a, 2)} rupees`;   // e.g. a ₹5.5 dividend
  return `${intWords(Math.round(a))} rupees`;
}

const UNIT: Record<string, number> = {
  crore: 1e7, crores: 1e7, cr: 1e7, "cr.": 1e7,
  lakh: 1e5, lakhs: 1e5, lac: 1e5, lacs: 1e5, l: 1e5,
  billion: 1e9, bn: 1e9, million: 1e6, mn: 1e6,
  thousand: 1e3, k: 1e3,
};
const UNIT_RE = "crores?|cr\\.?|lakhs?|lacs?|l\\b|billion|bn|million|mn|thousand|k\\b";
const num = (s: string) => Number(s.replace(/,/g, ""));

/** Rewrite every figure in a sentence into words: rupee amounts ("₹4,265 cr",
 *  "Rs 1.2L", "73,882 crore"), percentages and plain numbers. */
export function speakable(text: string): string {
  let t = text.replace(/▲\s*/g, "up ").replace(/▼\s*/g, "down ").replace(/\s*·\s*/g, ", ");
  // ₹ / Rs / INR amounts, with or without a unit
  t = t.replace(new RegExp(`(?:₹|\\bRs\\.?|\\bINR)\\s*([\\d,]+(?:\\.\\d+)?)(?:\\s*(${UNIT_RE}))?`, "gi"),
    (_m, n: string, u?: string) => rupeesWords(num(n) * (u ? UNIT[u.toLowerCase()] ?? 1 : 1)));
  // signs in front of figures: "+120 bp", "(-3.2%)"
  t = t.replace(/(^|[\s(])\+(?=\d)/g, "$1plus ").replace(/(^|[\s(])[-−](?=\d)/g, "$1minus ");
  // "73,882 crore" without a rupee sign
  t = t.replace(/\b([\d,]+(?:\.\d+)?)\s*(crores?|cr\b\.?|lakhs?|lacs?)/gi,
    (_m, n: string, u: string) => rupeesWords(num(n) * (UNIT[u.toLowerCase()] ?? 1)));
  // percentages and basis points
  t = t.replace(/([+-]?)(\d[\d,]*(?:\.\d+)?)\s*%/g,
    (_m, s: string, n: string) => `${s === "-" ? "minus " : s === "+" ? "plus " : ""}${numberWords(num(n), 1)} percent`);
  t = t.replace(/(\d[\d,]*(?:\.\d+)?)\s*bp\b/gi, (_m, n: string) => `${numberWords(num(n))} basis points`);
  // anything left: plain numbers ("Q2" -> "Q two", "FY27" -> "F Y twenty seven")
  t = t.replace(/\bFY\s?(\d{2,4})\b/g, (_m, y: string) => `F Y ${numberWords(num(y))}`);
  t = t.replace(/\d[\d,]*(?:\.\d+)?/g, (n) => ` ${numberWords(num(n))} `);
  return t.replace(/\s+/g, " ").replace(/\s+([.,;:!?])/g, "$1").trim();
}
