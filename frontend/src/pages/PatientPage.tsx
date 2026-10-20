import { ActionIcon, Badge, Button, Group, Menu, Stack, Tabs, Text, Title } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import {
  IconClipboardList,
  IconDotsVertical,
  IconDownload,
  IconFiles,
  IconFileText,
  IconHistory,
  IconShieldCheck,
} from "@tabler/icons-react";
import { useState } from "react";
import { Outlet, useLocation, useNavigate, useParams } from "react-router-dom";
import { usePatients, validatePatient } from "../api/queries";
import { dataClassLabel } from "../lib/format";
import { useIsMobile } from "../lib/useIsMobile";

const TABS = [
  { value: "documents", label: "Документы", icon: IconFileText },
  { value: "measurements", label: "Опросники", icon: IconClipboardList },
  { value: "files", label: "Файлы", icon: IconFiles },
  { value: "history", label: "История", icon: IconHistory },
];

export function PatientPage() {
  const { code = "" } = useParams();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { data: patients } = usePatients();
  const patient = patients?.find((p) => p.code === code);
  const mobile = useIsMobile();
  const [checking, setChecking] = useState(false);

  const base = `/patients/${encodeURIComponent(code)}`;
  const exportUrl = `/api/patients/${encodeURIComponent(code)}/export.ttl`;
  const tab = TABS.find((t) => pathname.startsWith(`${base}/${t.value}`))?.value ?? "documents";

  const checkShacl = async () => {
    setChecking(true);
    try {
      const r = await validatePatient(code);
      notifications.show(
        r.conforms
          ? { color: "green", title: "Граф целостен", message: `Нарушений SHACL нет, троек: ${r.triples}` }
          : {
              color: "red",
              title: `Нарушений SHACL: ${r.violations.length}`,
              message: r.violations.slice(0, 3).map((v) => v.message).join("; "),
            },
      );
    } catch (e) {
      notifications.show({ color: "red", message: String((e as Error).message) });
    } finally {
      setChecking(false);
    }
  };

  return (
    <Stack gap="md">
      <Group justify="space-between" align="flex-start" wrap="nowrap" gap="sm">
        <Stack gap={2} style={{ minWidth: 0 }}>
          <Group gap="xs">
            <Title order={2} fz={{ base: "h3", sm: "h2" }}>
              {code}
            </Title>
            {patient && <Badge variant="light">{dataClassLabel(patient.data_class)}</Badge>}
          </Group>
          {patient && patient.aliases.length > 0 && (
            <Text size="sm" c="dimmed">
              Имя в опросниках: {patient.aliases.join(", ")}
            </Text>
          )}
        </Stack>
        {mobile ? (
          <Menu position="bottom-end" withinPortal>
            <Menu.Target>
              <ActionIcon variant="default" size="lg" aria-label="Действия с пациентом" loading={checking}>
                <IconDotsVertical size={18} />
              </ActionIcon>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item leftSection={<IconShieldCheck size={16} />} onClick={checkShacl}>
                Проверить целостность
              </Menu.Item>
              <Menu.Item leftSection={<IconDownload size={16} />} component="a" href={exportUrl} target="_blank">
                Выгрузка RDF
              </Menu.Item>
            </Menu.Dropdown>
          </Menu>
        ) : (
          <Group gap="xs" wrap="nowrap">
            <Button
              variant="default"
              leftSection={<IconShieldCheck size={16} />}
              onClick={checkShacl}
              loading={checking}
            >
              Проверить целостность
            </Button>
            <Button variant="subtle" leftSection={<IconDownload size={16} />} component="a" href={exportUrl} target="_blank">
              RDF
            </Button>
          </Group>
        )}
      </Group>

      {/* на телефоне вкладки делят ширину поровну и идут без значков, чтобы все четыре были видны */}
      <Tabs value={tab} onChange={(v) => v && navigate(`${base}/${v}`)}>
        <Tabs.List grow={mobile}>
          {TABS.map((t) => (
            <Tabs.Tab
              key={t.value}
              value={t.value}
              leftSection={mobile ? undefined : <t.icon size={16} />}
              px={mobile ? 4 : undefined}
              fz={mobile ? "sm" : undefined}
            >
              {t.label}
            </Tabs.Tab>
          ))}
        </Tabs.List>
      </Tabs>

      <Outlet />
    </Stack>
  );
}
