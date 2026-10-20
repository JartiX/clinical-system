import { Alert, Button, Code, Group, Modal, Stack, Text, TextInput, Textarea } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconAlertTriangle } from "@tabler/icons-react";
import { useState, type ReactNode } from "react";
import { useDeleteFile, useRestoreFile, useRetractFile } from "../../api/queries";
import type { SourceFileRow } from "../../api/types";
import { useIsMobile } from "../../lib/useIsMobile";

interface Props {
  file: SourceFileRow;
  onClose: () => void;
}

function ActionModal(props: { title: string; onClose: () => void; children: ReactNode }) {
  const mobile = useIsMobile();
  return (
    <Modal opened onClose={props.onClose} title={props.title} fullScreen={mobile} size="lg">
      {props.children}
    </Modal>
  );
}

const fail = (e: unknown) =>
  notifications.show({ color: "red", title: "Не получилось", message: String((e as Error).message) });

export function RetractFileModal({ file, onClose }: Props) {
  const retract = useRetractFile();
  const [reason, setReason] = useState("");
  const submit = async () => {
    try {
      await retract.mutateAsync({ id: file.id, reason });
      notifications.show({ color: "green", message: `Файл «${file.file_name}» отозван` });
      onClose();
    } catch (e) {
      fail(e);
    }
  };
  return (
    <ActionModal title="Отозвать файл" onClose={onClose}>
      <Stack>
        <Text>
          Из системы уберётся всё, что получено из файла <b>«{file.file_name}»</b>: документов —{" "}
          {file.documents_current}
          {file.facts_current ? `, измерений — ${file.facts_current}` : ""}. Файл останется в истории, его можно будет
          вернуть.
        </Text>
        <Textarea
          label="Причина"
          placeholder="Например: файл другого пациента"
          value={reason}
          onChange={(e) => setReason(e.currentTarget.value)}
          autosize
          minRows={2}
          required
          data-autofocus
        />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Отмена
          </Button>
          <Button onClick={submit} loading={retract.isPending} disabled={!reason.trim()}>
            Отозвать
          </Button>
        </Group>
      </Stack>
    </ActionModal>
  );
}

export function RestoreFileModal({ file, onClose }: Props) {
  const restore = useRestoreFile();
  const submit = async () => {
    try {
      await restore.mutateAsync(file.id);
      notifications.show({ color: "green", message: `Файл «${file.file_name}» снова используется` });
      onClose();
    } catch (e) {
      fail(e);
    }
  };
  return (
    <ActionModal title="Вернуть файл" onClose={onClose}>
      <Stack>
        <Text>
          Документы и измерения из файла <b>«{file.file_name}»</b> снова станут текущими. Если за это время появилась
          более новая версия того же документа, она останется на месте.
        </Text>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Отмена
          </Button>
          <Button onClick={submit} loading={restore.isPending}>
            Вернуть
          </Button>
        </Group>
      </Stack>
    </ActionModal>
  );
}

export function DeleteFileModal({ file, onClose }: Props) {
  const remove = useDeleteFile();
  const [reason, setReason] = useState("");
  const [confirm, setConfirm] = useState("");
  const submit = async () => {
    try {
      await remove.mutateAsync({ id: file.id, reason, confirmName: confirm });
      notifications.show({ color: "green", message: `Файл «${file.file_name}» удалён` });
      onClose();
    } catch (e) {
      fail(e);
    }
  };
  return (
    <ActionModal title="Удалить файл безвозвратно" onClose={onClose}>
      <Stack>
        <Alert color="red" variant="light" icon={<IconAlertTriangle />}>
          Файл и всё, что из него получено, будут стёрты без возможности восстановления. В истории останется только
          запись «файл удалён» с причиной. Используйте для данных, которые не должны храниться в этой карте, например
          для файла другого человека. Если файл просто лишний, лучше отозвать его.
        </Alert>
        <Textarea
          label="Причина"
          placeholder="Например: файл другого пациента"
          value={reason}
          onChange={(e) => setReason(e.currentTarget.value)}
          autosize
          minRows={2}
          required
        />
        <TextInput
          label={
            <>
              Для подтверждения введите имя файла: <Code>{file.file_name}</Code>
            </>
          }
          value={confirm}
          onChange={(e) => setConfirm(e.currentTarget.value)}
          autoComplete="off"
        />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Отмена
          </Button>
          <Button
            color="red"
            onClick={submit}
            loading={remove.isPending}
            disabled={!reason.trim() || confirm !== file.file_name}
          >
            Удалить безвозвратно
          </Button>
        </Group>
      </Stack>
    </ActionModal>
  );
}
