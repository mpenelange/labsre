# Security policy

LabSRE is experimental software that can eventually interact with infrastructure. The current
release implements replay mode only and must not be treated as a production remediation system.

Do not expose the API or MCP server to an untrusted network. Do not mount a Docker socket, SSH
agent, credential directory, or sensitive application data into the container.

Please report suspected vulnerabilities privately through GitHub's security-advisory feature.
Do not include real credentials, private logs, or personal data in a report.

