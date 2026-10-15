import { Anchor, Badge, Box, Button, Group, Paper, Stack, Text, Title } from "@mantine/core";
import { useState } from "react";
import { Link } from "react-router-dom";
import type { Measurement } from "../../api/types";
import { formatDate } from "../../lib/format";
import classes from "./MeasurementCard.module.css";

// длинные опросники показываются свёрнутыми, чтобы страница не растягивалась на десяток экранов
const COLLAPSED_ITEMS = 10;

export function MeasurementCard({ m, code }: { m: Measurement; code: string }) {
  const v = m.value;
  const source = m.sources[0];
  const long = v.items.length > COLLAPSED_ITEMS + 5;
  const [expanded, setExpanded] = useState(false);
  const items = long && !expanded ? v.items.slice(0, COLLAPSED_ITEMS) : v.items;
  return (
    <Paper withBorder p={{ base: "sm", sm: "md" }}>
      <Stack gap="xs">
        <Group justify="space-between" align="flex-start" wrap="nowrap" gap="sm">
          <Stack gap={0} style={{ minWidth: 0 }}>
            <Title order={4}>{v.instrument_name}</Title>
            <Text size="sm" c="dimmed">
              {formatDate(m.date)} · измерено · пунктов {v.items.length}
            </Text>
          </Stack>
          <Stack gap={0} align="flex-end">
            <Text size="xs" c="dimmed">
              сумма
            </Text>
            <Text fz={28} fw={700} lh={1}>
              {v.total ?? "—"}
            </Text>
          </Stack>
        </Group>

        {v.issues.length > 0 && (
          <Group gap={6}>
            {v.issues.map((i) => (
              <Badge key={i} color="orange" variant="light" tt="none" h="auto" py={2} style={{ whiteSpace: "normal" }}>
                {i}
              </Badge>
            ))}
          </Group>
        )}

        {/* пункты: на узком экране ответ уходит под формулировку, ничего не сжимается */}
        <Box className={classes.items}>
          {items.map((it) => (
            <div key={it.no} className={classes.row}>
              <Text size="sm" c="dimmed" className={classes.no}>
                {it.no}
              </Text>
              <Text size="sm" className={classes.question}>
                {it.text}
              </Text>
              <Text size="sm" className={classes.answer} c={it.answer ? undefined : "red"}>
                {it.answer ?? "нет ответа"}
              </Text>
              <Text size="sm" fw={600} className={classes.score}>
                {it.score ?? ""}
              </Text>
            </div>
          ))}
        </Box>
        {long && (
          <Button variant="subtle" size="xs" w="fit-content" onClick={() => setExpanded(!expanded)}>
            {expanded ? "Свернуть" : `Показать все ${v.items.length} пунктов`}
          </Button>
        )}

        {source && (
          <Anchor component={Link} to={`/patients/${encodeURIComponent(code)}/documents/${source.document_id}`} size="sm">
            Открыть строку таблицы
          </Anchor>
        )}
      </Stack>
    </Paper>
  );
}
