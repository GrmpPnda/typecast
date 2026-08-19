/**
 * Lightweight word-level diff: returns character ranges in `current` that differ from `original`.
 * Uses a simple LCS-based approach on words, then maps back to character positions.
 */

interface DiffRange {
  from: number;
  to: number;
}

function tokenize(text: string): { word: string; from: number; to: number }[] {
  const tokens: { word: string; from: number; to: number }[] = [];
  const re = /\S+/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    tokens.push({ word: m[0], from: m.index, to: m.index + m[0].length });
  }
  return tokens;
}

function lcsTable(a: string[], b: string[]): number[][] {
  const m = a.length;
  const n = b.length;
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] = a[i - 1] === b[j - 1]
        ? dp[i - 1][j - 1] + 1
        : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }
  return dp;
}

function lcsMatchedIndices(a: string[], b: string[]): Set<number> {
  const dp = lcsTable(a, b);
  const matched = new Set<number>();
  let i = a.length;
  let j = b.length;
  while (i > 0 && j > 0) {
    if (a[i - 1] === b[j - 1]) {
      matched.add(j - 1);
      i--;
      j--;
    } else if (dp[i - 1][j] >= dp[i][j - 1]) {
      i--;
    } else {
      j--;
    }
  }
  return matched;
}

export function diffRanges(original: string, current: string): DiffRange[] {
  if (!original || !current) return [];

  const oldTokens = tokenize(original);
  const newTokens = tokenize(current);

  const oldWords = oldTokens.map((t) => t.word);
  const newWords = newTokens.map((t) => t.word);

  const matched = lcsMatchedIndices(oldWords, newWords);

  const ranges: DiffRange[] = [];
  let runStart: number | null = null;

  for (let j = 0; j < newTokens.length; j++) {
    if (!matched.has(j)) {
      if (runStart === null) runStart = newTokens[j].from;
    } else {
      if (runStart !== null) {
        ranges.push({ from: runStart, to: newTokens[j - 1].to });
        runStart = null;
      }
    }
  }
  if (runStart !== null) {
    ranges.push({ from: runStart, to: newTokens[newTokens.length - 1].to });
  }

  return ranges;
}
