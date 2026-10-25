import { t } from "../app/i18n";
import type { PacketSummary } from "../api/types";
export function packetLabel(packet: PacketSummary) {
  return [
    t(`packet.purpose.${packet.purpose}`),
    packet.person_name || t("packet.noPerson"),
    packet.is_primary ? t("packet.primary") : t("packet.alternative"),
    packet.selected_version_id ? t("packet.savedVersion") : t("packet.empty"),
  ].join(" · ");
}
