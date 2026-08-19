declare module "typo-js" {
  class Typo {
    constructor(
      dictionary?: string,
      affData?: string | null,
      dicData?: string | null,
      settings?: { dictionaryPath?: string; flags?: Record<string, unknown> }
    );
    check(word: string): boolean;
    suggest(word: string, limit?: number): string[];
    dictionaryTable: Record<string, unknown[]>;
  }
  export = Typo;
}
