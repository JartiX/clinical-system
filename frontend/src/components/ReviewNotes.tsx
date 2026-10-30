import { Alert, Stack, Text } from "@mantine/core";
import { IconAlertCircle } from "@tabler/icons-react";
import type { ReviewNote } from "../api/types";

/** Замечания к документу. Обычный текст, а не список: так длинные строки без пробелов переносятся. */
export function ReviewNotes({ notes, title = "Требует проверки" }: { notes: ReviewNote[]; title?: string }) {
  if (!notes.length) return null;
  return (
    <Alert color="orange" variant="light" icon={<IconAlertCircle />} title={title}>
      <Stack gap={4}>
        {notes.map((n) => (
          <Text key={n.code + n.text} size="sm" style={{ overflowWrap: "anywhere" }}>
            {n.text}
          </Text>
        ))}
      </Stack>
    </Alert>
  );
}
