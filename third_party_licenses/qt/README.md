# Qt / PySide6 open-source distribution notice

The SUGAR Windows desktop application uses Qt through PySide6. SUGAR itself is licensed under Apache License 2.0; the Qt/PySide6 libraries remain separately licensed.

SUGAR's community Windows builds use the **LGPLv3 option** for the Qt/PySide6 components that are actually bundled with the application. The portable build keeps Qt libraries as replaceable shared-library files in the application directory rather than statically linking them into SUGAR.

The accompanying `LGPL-3.0.txt` and `GPL-3.0.txt` files reproduce the GNU Lesser General Public License version 3 and GNU General Public License version 3 terms. LGPLv3 incorporates GPLv3 and adds additional permissions.

Users may replace or modify LGPL-covered Qt libraries and may reverse engineer SUGAR to the extent necessary to debug modifications to those libraries, as required by the LGPL. SUGAR does not impose additional terms that restrict those LGPL rights.

## Corresponding source offer

For each distributed SUGAR Windows binary release that contains LGPL-covered Qt/PySide6 components, the SUGAR maintainers offer to provide the complete corresponding source code for the exact LGPL-covered Qt/PySide6 components used in that release, including any project-applied modifications (normally none), for no more than the reasonable cost of physically providing that source.

This offer is valid for at least three years from the date of the applicable binary release and for as long as SUGAR distributes or supports that binary release. To request the source, open a licensing/source request in the SUGAR GitHub repository identified in the application's `README-Windows.md` and include the SUGAR version and the PySide6/Qt version recorded in the bundled `licenses/manifest.json`.

Public release maintainers should also retain an archival copy of the corresponding Qt/PySide6 source for every distributed Windows release rather than relying solely on an upstream URL that could later change.

This notice applies only to LGPL-covered Qt/PySide6 components actually shipped with the SUGAR binary. A build must not add a GPL-only Qt module unless the licensing of the complete distributed application is separately reviewed and made compatible with that module's terms.
