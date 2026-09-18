function disabledPublicSurface(): never {
  throw new Error("Disabled public surface module was loaded");
}

export const listPublishedContent = disabledPublicSurface;
export const readPublishedContent = disabledPublicSurface;
export const presentContentIndex = disabledPublicSurface;
export const presentContentEntry = disabledPublicSurface;
export const presentServicesIndex = disabledPublicSurface;
export const presentCountry = disabledPublicSurface;
export const presentService = disabledPublicSurface;
export const readPublicLegalDocument = disabledPublicSurface;
export const legalSourceUrl = disabledPublicSurface;
