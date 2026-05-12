export interface PlantContextOption {
  reference: string;
  label: string;
  plantId?: number;
}

export function selectedPlantContext(
  plantOptions: PlantContextOption[],
  plantReference?: string,
) {
  if (!plantReference) return null;
  return (
    plantOptions.find((option) => option.reference === plantReference) ?? null
  );
}
