import { Button, Center, Stack, Text, Title } from "@mantine/core";
import { IconUpload } from "@tabler/icons-react";
import { useUpload } from "../features/upload/UploadContext";

export function HomePage() {
  const upload = useUpload();
  return (
    <Center mih="60vh">
      <Stack align="center" gap="sm" maw={460}>
        <Title order={3}>Выберите пациента</Title>
        <Text c="dimmed" ta="center">
          Слева список пациентов. Чтобы добавить нового, загрузите его файлы: медкарты, выписки, транскрипты бесед и
          таблицы опросников.
        </Text>
        <Button leftSection={<IconUpload size={16} />} onClick={() => upload.open()}>
          Загрузить файлы
        </Button>
      </Stack>
    </Center>
  );
}
