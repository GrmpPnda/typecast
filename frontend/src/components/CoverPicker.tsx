import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { listImages, listAllImages } from "@/api/images";
import ImagePickerModal from "./ImagePickerModal";

interface CoverPickerProps {
  workId: string;
  onSelectImage: (imageUrl: string) => void;
  onUpload: (file: File) => void;
  onClose: () => void;
}

export default function CoverPicker({ workId, onSelectImage, onUpload, onClose }: CoverPickerProps) {
  const [scope, setScope] = useState<"work" | "all">("work");

  const { data: workImages = [] } = useQuery({
    queryKey: ["images", workId],
    queryFn: () => listImages(workId),
  });

  const { data: allImages = [] } = useQuery({
    queryKey: ["images", "all"],
    queryFn: listAllImages,
    enabled: scope === "all",
  });

  const displayImages = scope === "work" ? workImages : allImages;

  return (
    <ImagePickerModal
      title="Choose Cover Image"
      images={displayImages}
      onSelect={(img) => onSelectImage(img.url)}
      onUpload={onUpload}
      onClose={onClose}
      filterTabs={[
        { key: "work", label: "This work" },
        { key: "all", label: "All images" },
      ]}
      activeFilter={scope}
      onFilterChange={(key) => setScope(key as "work" | "all")}
    />
  );
}
