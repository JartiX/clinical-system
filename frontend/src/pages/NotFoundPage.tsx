import { Anchor, Center, Stack, Text, Title } from "@mantine/core";
import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <Center mih="60vh">
      <Stack align="center" gap="xs">
        <Title order={3}>Страница не найдена</Title>
        <Text c="dimmed">Такого адреса нет.</Text>
        <Anchor component={Link} to="/">
          На главную
        </Anchor>
      </Stack>
    </Center>
  );
}
