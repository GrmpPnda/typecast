export interface Series {
  id: string;
  title: string;
  description: string;
  cover_image_path: string | null;
  sort_order: number;
  ai_instructions: string;
  created_at: string;
  updated_at: string;
}

export interface CreateSeries {
  title: string;
  description?: string;
  ai_instructions?: string;
}

export interface UpdateSeries {
  title?: string;
  description?: string;
  ai_instructions?: string;
}

export interface Work {
  id: string;
  title: string;
  subtitle: string | null;
  author: string;
  description: string | null;
  blurb: string | null;
  isbn: string | null;
  genre: string[];
  tags: string[];
  language: string;
  publisher: string | null;
  publication_date: string | null;
  edition: string | null;
  word_count_target: number | null;
  notes: string;
  ai_instructions: string;
  title_page_config: TitlePageConfig | null;
  series_id: string | null;
  sort_order: number;
  status: "draft" | "revision" | "complete" | "published";
  cover_image_path: string | null;
  website: string | null;
  default_profile_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateWork {
  title: string;
  author: string;
  subtitle?: string;
  description?: string;
  blurb?: string;
  isbn?: string;
  genre?: string[];
  tags?: string[];
  language?: string;
  publisher?: string;
  edition?: string;
  word_count_target?: number;
  notes?: string;
  ai_instructions?: string;
  title_page_config?: TitlePageConfig;
  series_id?: string;
  website?: string;
  default_profile_id?: string;
}

export interface UpdateWork {
  title?: string;
  author?: string;
  subtitle?: string;
  description?: string;
  blurb?: string;
  isbn?: string;
  genre?: string[];
  tags?: string[];
  language?: string;
  publisher?: string | null;
  publication_date?: string | null;
  edition?: string | null;
  word_count_target?: number | null;
  website?: string | null;
  notes?: string;
  ai_instructions?: string;
  title_page_config?: TitlePageConfig | null;
  series_id?: string | null;
  sort_order?: number;
  status?: Work["status"];
  default_profile_id?: string | null;
}

export interface Chapter {
  id: string;
  work_id: string;
  title: string | null;
  number: number | null;
  show_title: boolean;
  notes: string;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface CreateChapter {
  work_id: string;
  title?: string;
  number?: number;
  show_title?: boolean;
  sort_order?: number;
}

export interface UpdateChapter {
  title?: string;
  number?: number;
  show_title?: boolean;
  notes?: string;
  sort_order?: number;
}

export interface Scene {
  id: string;
  chapter_id: string;
  title: string | null;
  content: string;
  notes: string;
  sort_order: number;
  word_count: number;
  status: "outline" | "draft" | "revision" | "final";
  pov_character: string | null;
  checkpoint: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateScene {
  chapter_id: string;
  title?: string;
  content?: string;
  notes?: string;
  sort_order?: number;
  status?: Scene["status"];
  pov_character?: string;
}

export interface UpdateScene {
  title?: string;
  content?: string;
  notes?: string;
  sort_order?: number;
  status?: Scene["status"];
  pov_character?: string;
}

export type SectionType =
  | "half_title" | "title_page" | "copyright" | "dedication"
  | "epigraph" | "table_of_contents" | "foreword" | "preface"
  | "acknowledgments_front" | "introduction" | "prologue"
  | "epilogue" | "afterword" | "acknowledgments_back"
  | "appendix" | "glossary" | "bibliography" | "index"
  | "about_author" | "also_by" | "colophon";

export type SectionPlacement = "front_matter" | "back_matter";

export interface Section {
  id: string;
  work_id: string;
  section_type: SectionType;
  placement: SectionPlacement;
  title: string | null;
  content: string;
  notes: string;
  sort_order: number;
  include_in_toc: boolean;
  include_page_numbers: boolean;
  start_recto: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateSection {
  section_type: SectionType;
  placement: SectionPlacement;
  title?: string;
  content?: string;
  notes?: string;
  sort_order?: number;
  include_in_toc?: boolean;
  include_page_numbers?: boolean;
  start_recto?: boolean;
}

export interface UpdateSection {
  title?: string;
  content?: string;
  notes?: string;
  sort_order?: number;
  include_in_toc?: boolean;
  include_page_numbers?: boolean;
  start_recto?: boolean;
}

export interface CodexImage {
  id: string;
  codex_entry_id: string;
  filename: string;
  original_name: string;
  mime_type: string;
  size_bytes: number;
  width: number | null;
  height: number | null;
  alt_text: string;
  is_primary: boolean;
  url: string;
  created_at: string;
  updated_at: string;
}

export interface UpdateCodexImage {
  alt_text?: string;
  is_primary?: boolean;
}

export interface CodexEntry {
  id: string;
  entry_type: "character" | "location" | "event" | "species" | "item" | "timeline" | "custom";
  name: string;
  description: string | null;
  content: string;
  notes: string;
  tags: string[];
  metadata: Record<string, any>;
  voice_id: string | null;
  work_ids: string[];
  series_ids: string[];
  images: CodexImage[];
  primary_image_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateCodexEntry {
  entry_type: CodexEntry["entry_type"];
  name: string;
  description?: string;
  content?: string;
  notes?: string;
  tags?: string[];
  metadata?: Record<string, any>;
  voice_id?: string;
  work_ids?: string[];
  series_ids?: string[];
}

export interface UpdateCodexEntry {
  entry_type?: CodexEntry["entry_type"];
  name?: string;
  description?: string;
  content?: string;
  notes?: string;
  tags?: string[];
  metadata?: Record<string, any>;
  voice_id?: string | null;
  work_ids?: string[];
  series_ids?: string[];
}

export interface WorkImage {
  id: string;
  work_id: string;
  filename: string;
  original_name: string;
  mime_type: string;
  size_bytes: number;
  width: number | null;
  height: number | null;
  alt_text: string;
  caption: string;
  tags: string;
  url: string;
  created_at: string;
  updated_at: string;
}

export interface UpdateImage {
  alt_text?: string;
  caption?: string;
  tags?: string;
}

export type ProfileFormat = "pdf" | "epub";
export type PageNumberPosition = "center" | "left" | "right" | "outside";
export type HeaderContent = "title" | "author" | "chapter" | "chapter_title" | "page_number" | "";
export type FooterContent = "title" | "author" | "chapter" | "chapter_title" | "page_number" | "";
export type HeaderPosition = "center" | "outer";
export type TextAlign = "justify" | "left" | "right" | "center";

export interface Profile {
  id: string;
  name: string;
  format: ProfileFormat;
  description: string;
  is_builtin: boolean;
  page_width: number | null;
  page_height: number | null;
  margin_top: number | null;
  margin_bottom: number | null;
  margin_inner: number | null;
  margin_outer: number | null;
  font_family: string;
  font_size: string;
  line_height: number;
  header_footer: boolean;
  include_cover: boolean;
  include_toc: boolean;
  page_numbers: boolean;
  page_number_position: PageNumberPosition;
  page_numbers_start_at_content: boolean;
  header_recto: HeaderContent | null;
  header_verso: HeaderContent | null;
  header_position: HeaderPosition;
  header_font_family: string | null;
  header_font_size: string | null;
  header_margin_top: number | null;
  header_from_edge: number | null;
  footer_margin_bottom: number | null;
  footer_from_edge: number | null;
  footer_recto: string | null;
  footer_verso: string | null;
  footer_position: string;
  header_font_weight: string | null;
  front_matter_roman: boolean;
  text_align: TextAlign;
  chapter_font_family: string | null;
  chapter_font_size: string | null;
  chapter_font_weight: string | null;
  chapter_align: string | null;
  chapter_sink: number | null;
  chapters_start_recto: boolean;
  back_matter_page_numbers: boolean;
  extra: Record<string, any> | null;
  created_at: string;
  updated_at: string;
}

export interface CreateProfile {
  name: string;
  format: ProfileFormat;
  description?: string;
  page_width?: number;
  page_height?: number;
  margin_top?: number;
  margin_bottom?: number;
  margin_inner?: number;
  margin_outer?: number;
  font_family?: string;
  font_size?: string;
  line_height?: number;
  header_footer?: boolean;
  include_cover?: boolean;
  include_toc?: boolean;
  page_numbers?: boolean;
  page_number_position?: PageNumberPosition;
  page_numbers_start_at_content?: boolean;
  header_recto?: HeaderContent;
  header_verso?: HeaderContent;
  header_position?: HeaderPosition;
  header_font_family?: string;
  header_font_size?: string;
  header_margin_top?: number;
  header_from_edge?: number;
  footer_margin_bottom?: number;
  footer_from_edge?: number;
  footer_recto?: string;
  footer_verso?: string;
  footer_position?: string;
  header_font_weight?: string;
  front_matter_roman?: boolean;
  text_align?: TextAlign;
  chapter_font_family?: string;
  chapter_font_size?: string;
  chapter_font_weight?: string;
  chapter_align?: string;
  chapter_sink?: number;
  chapters_start_recto?: boolean;
  back_matter_page_numbers?: boolean;
}

export interface UpdateProfile {
  name?: string;
  description?: string;
  page_width?: number | null;
  page_height?: number | null;
  margin_top?: number | null;
  margin_bottom?: number | null;
  margin_inner?: number | null;
  margin_outer?: number | null;
  font_family?: string;
  font_size?: string;
  line_height?: number;
  header_footer?: boolean;
  include_cover?: boolean;
  include_toc?: boolean;
  page_numbers?: boolean;
  page_number_position?: PageNumberPosition;
  page_numbers_start_at_content?: boolean;
  header_recto?: HeaderContent | null;
  header_verso?: HeaderContent | null;
  header_position?: HeaderPosition;
  header_font_family?: string | null;
  header_font_size?: string | null;
  header_margin_top?: number | null;
  header_from_edge?: number | null;
  footer_margin_bottom?: number | null;
  footer_from_edge?: number | null;
  footer_recto?: string | null;
  footer_verso?: string | null;
  footer_position?: string;
  header_font_weight?: string | null;
  front_matter_roman?: boolean;
  text_align?: TextAlign;
  chapter_font_family?: string | null;
  chapter_font_size?: string | null;
  chapter_font_weight?: string | null;
  chapter_align?: string | null;
  chapter_sink?: number | null;
  chapters_start_recto?: boolean;
  back_matter_page_numbers?: boolean;
}

export interface TitlePageConfig {
  title_override?: string | null;
  subtitle_override?: string | null;
  author_override?: string | null;
  title_font_family?: string | null;
  title_font_size?: string | null;
  subtitle_font_family?: string | null;
  subtitle_font_size?: string | null;
  author_font_family?: string | null;
  author_font_size?: string | null;
  author_position?: "after_subtitle" | "bottom" | null;
  ornament_image_url?: string | null;
}

export interface Font {
  id: string;
  filename: string;
  original_name: string;
  family_name: string;
  style: string;
  mime_type: string;
  size_bytes: number;
  url: string;
  created_at: string;
  updated_at: string;
}

export interface Comment {
  id: string;
  scene_id: string;
  anchor_text: string;
  anchor_from: number;
  anchor_to: number;
  content: string;
  suggestion: string | null;
  author: string;
  resolved: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateComment {
  anchor_text?: string;
  anchor_from?: number;
  anchor_to?: number;
  content?: string;
  suggestion?: string;
  author?: string;
}

export interface UpdateComment {
  content?: string;
  resolved?: boolean;
}
