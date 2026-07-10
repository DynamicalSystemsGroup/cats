output "docker_compose_ipfs_transport_id" {
  description = "Identifier of the shell_script resource that brings up the IPFS transport containers; used by module.plant's depends_on to sequence after this module."
  value       = shell_script.docker_compose_ipfs_transport.id
}
