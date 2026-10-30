import {
  Alert,
  Button,
  CloseButton,
  Group,
  Modal,
  Radio,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { Dropzone } from "@mantine/dropzone";
import { IconAlertTriangle, IconFile, IconUpload, IconX } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { checkFiles, previewTableNames, usePatients, useUploadFiles } from "../../api/queries";
import type { NameConflict, TableNames, UploadResult } from "../../api/types";
import { DATA_CLASS_OPTIONS, formatDateTime, nameKey, sha256 } from "../../lib/format";
import { useIsMobile } from "../../lib/useIsMobile";
import { AliasPicker, mergeNames } from "./AliasPicker";
import { IngestReportView } from "./IngestReportView";

type Choice = "version" | "separate";

// Заранее читаем имена только из файлов, похожих на таблицы; вид файла окончательно определяет сервер.
const looksLikeTable = (f: File) => /\.(xlsx|xls|csv)$/i.test(f.name);

interface Props {
  initialCode: string;
  onClose: () => void;
}

/** Загрузка файлов пациента: выбор файлов, проверка совпадающих имён, отчёт и ввод недостающих дат. */
export function UploadModal({ initialCode, onClose }: Props) {
  const navigate = useNavigate();
  const upload = useUploadFiles();
  const mobile = useIsMobile();
  const { data: patients } = usePatients();
  const [code, setCode] = useState(initialCode);
  const [dataClass, setDataClass] = useState("synthetic");
  const [aliases, setAliases] = useState<string[]>([]);
  // у существующего пациента класс данных и имена берутся из хранилища
  const existing = patients?.find((p) => p.code === code.trim());
  const effectiveClass = existing?.data_class ?? dataClass;
  const knownAliases = existing?.aliases ?? [];
  const [files, setFiles] = useState<File[]>([]);
  const [tables, setTables] = useState<TableNames[] | null>(null);
  const [readingNames, setReadingNames] = useState(false);

  // имена из таблиц опросников читаются сразу после выбора файлов
  const tableFiles = files.filter(looksLikeTable);
  const tablesKey = tableFiles.map((f) => `${f.name}:${f.size}:${f.lastModified}`).join("|");
  useEffect(() => {
    if (!tablesKey) {
      setTables(null);
      return;
    }
    let cancelled = false;
    setReadingNames(true);
    previewTableNames(tableFiles)
      .then(({ tables: found }) => {
        if (cancelled) return;
        setTables(found);
        const available = new Set(mergeNames(found).map((n) => nameKey(n.name)));
        setAliases((prev) => {
          const kept = prev.filter((a) => available.has(nameKey(a)));
          if (kept.length || knownAliases.length) return kept;
          // единственный человек во всех таблицах — скорее всего, это и есть пациент
          const all = mergeNames(found);
          return all.length === 1 ? [all[0].name] : [];
        });
      })
      .catch(() => !cancelled && setTables(null))
      .finally(() => !cancelled && setReadingNames(false));
    return () => {
      cancelled = true;
    };
    // tableFiles меняется на каждом рендере, его содержимое отражает tablesKey
  }, [tablesKey]);
  const [conflicts, setConflicts] = useState<NameConflict[] | null>(null);
  const [choices, setChoices] = useState<Record<string, Choice>>({});
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<UploadResult | null>(null);

  const addFiles = (added: File[]) => {
    setFiles((prev) => [...prev.filter((p) => !added.some((a) => a.name === p.name)), ...added]);
    setConflicts(null);
  };

  const send = async (separate: string[]) => {
    setError(null);
    try {
      setResult(await upload.mutateAsync({ code: code.trim(), files, dataClass: effectiveClass, aliases, separate }));
    } catch (e) {
      setError(String((e as Error).message));
    }
  };

  const submit = async () => {
    // если совпадения уже показаны, отправляем с выбранными ответами
    if (conflicts) {
      return send(conflicts.filter((c) => choices[c.file] === "separate").map((c) => c.file));
    }
    setChecking(true);
    setError(null);
    try {
      const fingerprints = await Promise.all(files.map(async (f) => ({ name: f.name, sha256: await sha256(f) })));
      const found = (await checkFiles(code.trim(), fingerprints)).conflicts;
      if (found.length) {
        setConflicts(found);
        return;
      }
      await send([]);
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setChecking(false);
    }
  };

  const unresolved = conflicts?.some((c) => !choices[c.file]) ?? false;

  if (result) {
    return (
      <Modal opened onClose={onClose} title="Отчёт о приёме" size="xl" closeOnEscape={false} fullScreen={mobile}>
        <IngestReportView result={result} />
        <Group justify="flex-end" mt="md">
          <Button variant="default" onClick={onClose}>
            Закрыть
          </Button>
          <Button
            onClick={() => {
              onClose();
              navigate(`/patients/${encodeURIComponent(result.report.patient)}/documents`);
            }}
          >
            Открыть пациента
          </Button>
        </Group>
      </Modal>
    );
  }

  return (
    <Modal opened onClose={onClose} title="Загрузка файлов пациента" size="lg" fullScreen={mobile}>
      <Stack>
        <TextInput
          label="Код пациента"
          description="Под этим кодом пациент появится в списке. Если код уже есть, файлы добавятся к нему."
          value={code}
          onChange={(e) => setCode(e.currentTarget.value)}
          required
        />
        <SimpleGrid cols={{ base: 1, xs: 2 }} spacing="sm">
          <Select
            label="Класс данных"
            description={existing ? "задан при первой загрузке пациента" : undefined}
            data={DATA_CLASS_OPTIONS}
            value={effectiveClass}
            onChange={(v) => v && setDataClass(v)}
            allowDeselect={false}
            disabled={!!existing}
          />
        </SimpleGrid>

        <Dropzone onDrop={addFiles} multiple>
          <Group justify="center" gap="md" mih={110} wrap={mobile ? "wrap" : "nowrap"} style={{ pointerEvents: "none" }}>
            <Dropzone.Accept>
              <IconUpload size={40} stroke={1.5} />
            </Dropzone.Accept>
            <Dropzone.Reject>
              <IconX size={40} stroke={1.5} />
            </Dropzone.Reject>
            <Dropzone.Idle>
              <IconFile size={40} stroke={1.5} />
            </Dropzone.Idle>
            <div>
              <Text size="lg" ta={mobile ? "center" : undefined}>
                {mobile ? "Нажмите, чтобы выбрать файлы" : "Перетащите файлы сюда или нажмите, чтобы выбрать"}
              </Text>
              <Text size="sm" c="dimmed">
                Медкарты и выписки (TXT, DOCX), транскрипты бесед (TXT), опросники (XLSX, CSV). Дата берётся из имени
                файла, например <span style={{ whiteSpace: "nowrap" }}>«беседа 2025-10-20.txt»</span>; если её нет,
                укажете после загрузки.
              </Text>
            </div>
          </Group>
        </Dropzone>

        {files.length > 0 && (
          <Stack gap={4}>
            {files.map((f) => (
              <Group key={f.name} justify="space-between" wrap="nowrap" align="flex-start">
                <Text size="sm" style={{ minWidth: 0 }}>
                  {f.name}
                </Text>
                <Group gap="xs" wrap="nowrap">
                  <Text size="xs" c="dimmed">
                    {(f.size / 1024).toFixed(1)} КБ
                  </Text>
                  <CloseButton
                    size="sm"
                    aria-label="Убрать файл"
                    onClick={() => {
                      setFiles(files.filter((x) => x !== f));
                      setConflicts(null);
                    }}
                  />
                </Group>
              </Group>
            ))}
          </Stack>
        )}

        <AliasPicker
          tables={tables}
          loading={readingNames}
          known={knownAliases}
          selected={aliases}
          onChange={setAliases}
        />

        {conflicts && (
          <Alert color="yellow" icon={<IconAlertTriangle />} title="Файлы с такими именами уже загружены">
            <Stack gap="sm">
              <Text size="sm">
                Содержимое отличается. Это исправленная версия прежнего файла или другой документ?
              </Text>
              {conflicts.map((c) => (
                <Stack key={c.file} gap={4}>
                  <Text size="sm" fw={500}>
                    {c.file}{" "}
                    <Text span size="xs" c="dimmed">
                      (прежний загружен {formatDateTime(c.existing_received_at)})
                    </Text>
                  </Text>
                  <Radio.Group
                    value={choices[c.file] ?? null}
                    onChange={(v) => setChoices({ ...choices, [c.file]: v as Choice })}
                  >
                    <Group gap="lg" mt={4}>
                      <Radio size="sm" value="version" label="Исправленная версия прежнего" />
                      <Radio size="sm" value="separate" label="Другой документ, сохранить отдельно" />
                    </Group>
                  </Radio.Group>
                </Stack>
              ))}
            </Stack>
          </Alert>
        )}

        {error && (
          <Alert color="red" title="Не удалось загрузить">
            {error}
          </Alert>
        )}

        <Group justify="flex-end" mt="xs">
          <Button variant="default" onClick={onClose}>
            Отмена
          </Button>
          <Button
            onClick={submit}
            loading={checking || upload.isPending}
            disabled={!code.trim() || files.length === 0 || unresolved || readingNames}
          >
            Загрузить
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
