declare module "virtual:career-bootstrap" {
  const catalogs: Record<"en" | "ru", import("./i18n").LocaleCatalog>;
  export default catalogs;
}
