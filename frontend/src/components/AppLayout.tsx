import {
  ActionIcon,
  AppShell,
  Burger,
  Button,
  Group,
  Title,
  Tooltip,
  useComputedColorScheme,
  useMantineColorScheme,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { IconMoon, IconSun, IconUpload } from "@tabler/icons-react";
import { Link, Outlet } from "react-router-dom";
import { UploadProvider, useUpload } from "../features/upload/UploadContext";
import { useCurrentPatientCode } from "../lib/useCurrentPatient";
import { useIsMobile } from "../lib/useIsMobile";
import { PatientNav } from "./PatientNav";

export function AppLayout() {
  return (
    <UploadProvider>
      <Shell />
    </UploadProvider>
  );
}

function Shell() {
  const [opened, { toggle, close }] = useDisclosure();
  const { setColorScheme } = useMantineColorScheme();
  // при теме «как в системе» colorScheme равен "auto"; реальная тема — computed
  const scheme = useComputedColorScheme("light");
  const upload = useUpload();
  const code = useCurrentPatientCode();
  const mobile = useIsMobile();

  return (
    <AppShell
      header={{ height: 56 }}
      navbar={{ width: { sm: 240, lg: 280 }, breakpoint: "sm", collapsed: { mobile: !opened } }}
      padding={{ base: "sm", sm: "md" }}
    >
      <AppShell.Header>
        <Group h="100%" px={{ base: "sm", sm: "md" }} justify="space-between" wrap="nowrap" gap="xs">
          <Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}>
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" aria-label="Список пациентов" />
            <Link to="/" style={{ color: "inherit", textDecoration: "none", minWidth: 0 }} onClick={close}>
              <Title order={4} fz={{ base: "md", sm: "lg" }} lh={1.2}>
                Клиническое рассуждение
              </Title>
            </Link>
          </Group>
          <Group gap="xs" wrap="nowrap">
            {mobile ? (
              <ActionIcon size="lg" onClick={() => upload.open(code)} aria-label="Загрузить файлы">
                <IconUpload size={18} />
              </ActionIcon>
            ) : (
              <Button leftSection={<IconUpload size={16} />} onClick={() => upload.open(code)}>
                Загрузить файлы
              </Button>
            )}
            <Tooltip label={scheme === "dark" ? "Светлая тема" : "Тёмная тема"}>
              <ActionIcon
                variant="default"
                size="lg"
                onClick={() => setColorScheme(scheme === "dark" ? "light" : "dark")}
                aria-label="Сменить тему"
              >
                {scheme === "dark" ? <IconSun size={18} /> : <IconMoon size={18} />}
              </ActionIcon>
            </Tooltip>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="sm">
        <PatientNav onNavigate={close} />
      </AppShell.Navbar>

      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
