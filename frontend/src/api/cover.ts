import client from "./client";

export interface CoverDimensions {
  trim_width: number;
  trim_height: number;
  page_count: number;
  spine_width: number;
  bleed: number;
  total_width: number;
  total_height: number;
  front_x: number;
  spine_x: number;
  back_x: number;
  total_width_px: number;
  total_height_px: number;
  cover_type: string;
  flap_width?: number;
  front_flap_x?: number;
  back_flap_x?: number;
}

export interface CoverGenerateRequest {
  trim_width: number;
  trim_height: number;
  page_count: number;
  spine_factor?: number;
  cover_type?: string;
  front_image_path?: string | null;
  back_image_path?: string | null;
  spine_text?: string;
  back_title?: string;
  back_blurb?: string;
  background_color?: string;
  text_color?: string;
  spine_font_family?: string | null;
  blurb_font_family?: string | null;
  barcode_zone?: boolean;
  back_overlay_opacity?: number;
  back_logo_path?: string | null;
  back_website?: string;
  flap_width?: number;
  front_flap_text?: string;
  back_flap_text?: string;
  output_format?: string;
}

export async function getCoverDimensions(
  trimWidth: number,
  trimHeight: number,
  pageCount: number,
  spineFactor?: number,
  coverType?: string,
  flapWidth?: number
): Promise<CoverDimensions> {
  const { data } = await client.post<CoverDimensions>("/cover/dimensions", {
    trim_width: trimWidth,
    trim_height: trimHeight,
    page_count: pageCount,
    spine_factor: spineFactor ?? 0.0025,
    cover_type: coverType ?? "paperback",
    flap_width: flapWidth ?? 3.5,
  });
  return data;
}

export async function previewCover(
  workId: string,
  req: CoverGenerateRequest
): Promise<string> {
  const { data } = await client.post(`/cover/${workId}/preview`, req, {
    responseType: "blob",
  });
  return URL.createObjectURL(data);
}

export async function downloadCover(
  workId: string,
  req: CoverGenerateRequest
): Promise<Blob> {
  const { data } = await client.post(`/cover/${workId}/generate`, req, {
    responseType: "blob",
  });
  return data;
}
