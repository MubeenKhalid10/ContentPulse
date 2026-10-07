"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { BriefcaseIcon, MoreHorizontalIcon, PlusIcon } from "lucide-react";
import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { fieldAria, FormField } from "@/components/shared/form-field";
import { PageHeader, ReadOnlyNotice } from "@/components/shared/page-header";
import { SimpleSelect } from "@/components/shared/simple-select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import {
  useCreateService,
  useDeleteService,
  useServices,
  useUpdateService,
} from "@/hooks/use-organization";
import { errorMessage } from "@/lib/api";
import { useCan } from "@/lib/auth";
import { OFFERING_KIND_OPTIONS } from "@/lib/options";
import { serviceSchema } from "@/schemas/organization";
import type { OrganizationService } from "@/types/api";

type Input = z.input<typeof serviceSchema>;
type Output = z.output<typeof serviceSchema>;

const kindLabel = (kind: OrganizationService["kind"]) =>
  OFFERING_KIND_OPTIONS.find((o) => o.value === kind)?.label ?? kind;

export function ServicesManager() {
  const services = useServices();
  const canEdit = useCan()("organization.write");
  // undefined = closed, null = creating, object = editing
  const [editing, setEditing] = useState<OrganizationService | null | undefined>(undefined);
  const [deleting, setDeleting] = useState<OrganizationService | undefined>(undefined);

  return (
    <>
      <PageHeader
        title="Services & products"
        description="What you offer. Trends are matched against this list, and posts never claim an offering that isn't on it."
        actions={
          canEdit && (
            <Button onClick={() => setEditing(null)}>
              <PlusIcon />
              Add
            </Button>
          )
        }
      />
      {!canEdit && <ReadOnlyNotice />}

      {services.isPending ? (
        <Card>
          <CardContent className="grid gap-3">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </CardContent>
        </Card>
      ) : services.data?.length ? (
        <Card className="py-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">Name</TableHead>
                <TableHead>Type</TableHead>
                <TableHead className="hidden md:table-cell">Category</TableHead>
                <TableHead>Active</TableHead>
                {canEdit && <TableHead className="w-12" />}
              </TableRow>
            </TableHeader>
            <TableBody>
              {services.data.map((service) => (
                <ServiceRow
                  key={service.id}
                  service={service}
                  canEdit={canEdit}
                  onEdit={() => setEditing(service)}
                  onDelete={() => setDeleting(service)}
                />
              ))}
            </TableBody>
          </Table>
        </Card>
      ) : (
        <Card>
          <CardContent className="grid justify-items-center gap-3 py-10 text-center">
            <span className="grid size-10 place-items-center rounded-full bg-muted">
              <BriefcaseIcon className="size-5 text-muted-foreground" />
            </span>
            <div className="grid gap-1">
              <p className="font-medium">No services yet</p>
              <p className="max-w-sm text-sm text-muted-foreground">
                Add the services, products and areas of expertise you want content to connect
                trends to.
              </p>
            </div>
            {canEdit && (
              <Button variant="outline" onClick={() => setEditing(null)}>
                <PlusIcon />
                Add your first service
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      <ServiceDialog editing={editing} onClose={() => setEditing(undefined)} />
      <DeleteServiceDialog service={deleting} onClose={() => setDeleting(undefined)} />
    </>
  );
}

function ServiceRow({
  service,
  canEdit,
  onEdit,
  onDelete,
}: {
  service: OrganizationService;
  canEdit: boolean;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const update = useUpdateService();
  return (
    <TableRow>
      <TableCell className="max-w-md pl-4 whitespace-normal">
        <div className="font-medium">{service.name}</div>
        {service.description && (
          <div className="line-clamp-2 text-xs text-muted-foreground">{service.description}</div>
        )}
      </TableCell>
      <TableCell>
        <Badge variant="secondary">{kindLabel(service.kind)}</Badge>
      </TableCell>
      <TableCell className="hidden text-muted-foreground md:table-cell">
        {service.category ?? "—"}
      </TableCell>
      <TableCell>
        <Switch
          checked={service.active}
          disabled={!canEdit || update.isPending}
          aria-label={`${service.name} active`}
          onCheckedChange={(active) =>
            update.mutate(
              { serviceId: service.id, active },
              { onError: (e) => toast.error(errorMessage(e)) },
            )
          }
        />
      </TableCell>
      {canEdit && (
        <TableCell>
          <DropdownMenu>
            <DropdownMenuTrigger
              render={<Button variant="ghost" size="icon-sm" aria-label={`Actions for ${service.name}`} />}
            >
              <MoreHorizontalIcon />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-36">
              <DropdownMenuItem onClick={onEdit}>Edit</DropdownMenuItem>
              <DropdownMenuItem variant="destructive" onClick={onDelete}>
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </TableCell>
      )}
    </TableRow>
  );
}

function ServiceDialog({
  editing,
  onClose,
}: {
  editing: OrganizationService | null | undefined;
  onClose: () => void;
}) {
  return (
    <Dialog open={editing !== undefined} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        {editing !== undefined && (
          <ServiceForm key={editing?.id ?? "new"} service={editing} onDone={onClose} />
        )}
      </DialogContent>
    </Dialog>
  );
}

function ServiceForm({ service, onDone }: { service: OrganizationService | null; onDone: () => void }) {
  const create = useCreateService();
  const update = useUpdateService();
  const pending = create.isPending || update.isPending;
  const form = useForm<Input, unknown, Output>({
    resolver: zodResolver(serviceSchema),
    defaultValues: {
      kind: service?.kind ?? "service",
      name: service?.name ?? "",
      category: service?.category ?? "",
      description: service?.description ?? "",
      active: service?.active ?? true,
    },
  });
  const { errors } = form.formState;

  const onSubmit = form.handleSubmit((values) => {
    const options = {
      onSuccess: () => {
        toast.success(service ? "Saved" : `${values.name} added`);
        onDone();
      },
      onError: (e: unknown) => toast.error(errorMessage(e)),
    };
    if (service) update.mutate({ serviceId: service.id, ...values }, options);
    else create.mutate(values, options);
  });

  return (
    <form onSubmit={onSubmit} noValidate className="grid gap-5">
      <DialogHeader>
        <DialogTitle>{service ? `Edit ${service.name}` : "Add a service, product or expertise"}</DialogTitle>
        <DialogDescription>
          Describe it the way you&apos;d explain it to a new hire. Specific beats generic.
        </DialogDescription>
      </DialogHeader>
      <div className="grid gap-4 sm:grid-cols-3">
        <FormField id="kind" label="Type">
          <Controller
            control={form.control}
            name="kind"
            render={({ field }) => (
              <SimpleSelect id="kind" value={field.value} onChange={field.onChange} options={OFFERING_KIND_OPTIONS} />
            )}
          />
        </FormField>
        <FormField id="svc-name" label="Name" error={errors.name?.message} className="sm:col-span-2">
          <Input
            {...fieldAria("svc-name", errors.name?.message)}
            placeholder="e.g. AI Solutions"
            autoFocus
            {...form.register("name")}
          />
        </FormField>
      </div>
      <FormField id="category" label="Category" hint="Optional grouping, e.g. Engineering." error={errors.category?.message}>
        <Input {...fieldAria("category", errors.category?.message)} {...form.register("category")} />
      </FormField>
      <FormField id="svc-description" label="Description" error={errors.description?.message}>
        <Textarea
          {...fieldAria("svc-description", errors.description?.message)}
          rows={4}
          placeholder="What it is, who it's for, and the outcomes it delivers."
          {...form.register("description")}
        />
      </FormField>
      <Controller
        control={form.control}
        name="active"
        render={({ field }) => (
          <div className="flex items-center gap-3">
            <Switch id="active" checked={field.value} onCheckedChange={field.onChange} />
            <Label htmlFor="active" className="font-normal">
              Active — consider it when matching trends
            </Label>
          </div>
        )}
      />
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={pending}>
          {pending ? "Saving…" : service ? "Save" : "Add"}
        </Button>
      </DialogFooter>
    </form>
  );
}

function DeleteServiceDialog({
  service,
  onClose,
}: {
  service: OrganizationService | undefined;
  onClose: () => void;
}) {
  const remove = useDeleteService();
  return (
    <AlertDialog open={!!service} onOpenChange={(open) => !open && onClose()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete {service?.name}?</AlertDialogTitle>
          <AlertDialogDescription>
            Trends will no longer be matched against it. To pause it instead, switch it to
            inactive.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            disabled={remove.isPending}
            onClick={() =>
              service &&
              remove.mutate(service.id, {
                onSuccess: () => {
                  toast.success(`${service.name} deleted`);
                  onClose();
                },
                onError: (e) => toast.error(errorMessage(e)),
              })
            }
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
