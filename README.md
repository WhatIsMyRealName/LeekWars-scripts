# Python scripts for Leek Wars

This repository provides Python scripts that use the Leek Wars API to
collect public game data and produce statistics for the community.

## API usage and Terms of Use

The [Leek Wars Terms of Use](https://leekwars.com/conditions) now explicitly
allow automation, including through the public API and the official MCP
server. Third-party scripts are therefore no longer described as merely
tolerated: creating, using and distributing them is allowed within the
limits set out in the terms.

The scripts in this repository fit that permitted use:

- They access information publicly exposed by the API, without authentication.
- They analyse game data locally rather than controlling player accounts.
- They do not exploit bugs, bypass game restrictions or provide prohibited
  advantages.
- They do not automate farming or acquire in-game resources.

Their purpose is to provide useful statistics and analysis tools for the
whole community. They have also been shared on the
[official forum](https://leekwars.com/forum/category-6/topic-10448/page-7#message-69207),
where the discussion provides context about their use.

The absence of authentication is not, by itself, a guarantee that every
possible use is permitted. Users must still avoid excessive request volumes,
respect other players' privacy and comply with the current Terms of Use.
Leek Wars may restrict API access if its use disrupts the service.

These scripts are community-maintained and are not official Leek Wars tools.

## Official resources

Leek Wars provides [API documentation](https://leekwars.com/help/api) and an
[official MCP server](https://www.npmjs.com/package/@leek-wars/mcp).
The [combat action documentation](https://leekwars.com/encyclopedia/fr/Documentation_sur_le_retour_des_API)
also explains how to interpret fight reports.