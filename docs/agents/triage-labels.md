# Triage Labels

The engineering skills use five canonical triage roles. Local Markdown issues
record the corresponding string in their `Status:` line.

<table>
  <thead>
    <tr>
      <th>Canonical role</th>
      <th>Local status string</th>
      <th>Meaning</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><code>needs-triage</code></td>
      <td><code>needs-triage</code></td>
      <td>Maintainer needs to evaluate this issue</td>
    </tr>
    <tr>
      <td><code>needs-info</code></td>
      <td><code>needs-info</code></td>
      <td>Waiting on the reporter for more information</td>
    </tr>
    <tr>
      <td><code>ready-for-agent</code></td>
      <td><code>ready-for-agent</code></td>
      <td>Fully specified and ready for an AFK agent</td>
    </tr>
    <tr>
      <td><code>ready-for-human</code></td>
      <td><code>ready-for-human</code></td>
      <td>Requires human implementation or judgment</td>
    </tr>
    <tr>
      <td><code>wontfix</code></td>
      <td><code>wontfix</code></td>
      <td>Will not be actioned</td>
    </tr>
  </tbody>
</table>

When a skill mentions a canonical role, use the corresponding local status
string. Edit the middle column if this repo later adopts different vocabulary.
