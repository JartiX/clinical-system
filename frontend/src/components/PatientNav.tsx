import { Badge, Loader, NavLink, ScrollArea, Text, TextInput } from "@mantine/core";
import { IconSearch, IconUser } from "@tabler/icons-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useCurrentPatientCode } from "../lib/useCurrentPatient";
import { usePatients } from "../api/queries";
import { dataClassLabel } from "../lib/format";

export function PatientNav({ onNavigate }: { onNavigate: () => void }) {
  const { data, isLoading, error } = usePatients();
  const code = useCurrentPatientCode();
  const [query, setQuery] = useState("");

  const items = (data ?? []).filter((p) => p.code.toLowerCase().includes(query.toLowerCase()));

  return (
    <>
      <Text size="xs" fw={700} c="dimmed" tt="uppercase" mb="xs">
        Пациенты
      </Text>
      <TextInput
        size="xs"
        placeholder="Поиск по коду"
        leftSection={<IconSearch size={14} />}
        value={query}
        onChange={(e) => setQuery(e.currentTarget.value)}
        mb="xs"
      />
      {isLoading && <Loader size="sm" />}
      {error && (
        <Text size="sm" c="red">
          {String(error.message)}
        </Text>
      )}
      {data && data.length === 0 && (
        <Text size="sm" c="dimmed">
          Пациентов пока нет. Загрузите файлы.
        </Text>
      )}
      <ScrollArea flex={1}>
        {items.map((p) => (
          <NavLink
            key={p.code}
            component={Link}
            to={`/patients/${encodeURIComponent(p.code)}`}
            active={p.code === code}
            onClick={onNavigate}
            styles={{ label: { whiteSpace: "normal" }, description: { whiteSpace: "normal" } }}
            leftSection={<IconUser size={16} />}
            label={p.code}
            description={`${p.documents} док. · ${dataClassLabel(p.data_class)}`}
            rightSection={
              p.needs_review > 0 && (
                <Badge size="sm" color="orange" variant="light">
                  {p.needs_review}
                </Badge>
              )
            }
          />
        ))}
      </ScrollArea>
    </>
  );
}
