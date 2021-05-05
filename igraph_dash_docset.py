#!/usr/bin/env python

import urllib.request, json, tarfile, shutil, os
import sqlite3


def download_release():
    """
    Downloads the latest stable igraph release, and extracts the documentation to the html directory.
    """

    print("Looking for latest igraph release on GitHub ...")

    with urllib.request.urlopen(
        "https://api.github.com/repos/igraph/igraph/releases"
    ) as url:
        data = json.loads(url.read().decode())

    for entry in data:
        if not entry["prerelease"] and not entry["draft"]:
            release = entry
            break

    print("Found version %s. Downloading ..." % release["tag_name"])

    tarball = release["assets"][0]["browser_download_url"]
    stream = urllib.request.urlopen(tarball)
    tarfile.open(fileobj=stream, mode="r:gz").extractall()

    srcdir = "igraph-" + release["tag_name"]

    if os.path.isdir("html"):
        shutil.rmtree("html")

    shutil.move(os.path.join(srcdir, "doc", "html"), ".")
    shutil.rmtree(srcdir)

    return release["tag_name"]


def create_docset(docdir, docset_name="igraph"):
    """
    Creates a Dash docset from the igraph documentation in the given directory.
    """

    from glob import glob
    from bs4 import BeautifulSoup
    from lxml.html import parse, tostring, fromstring

    print("Creating docset ...")

    # Create directory structure and put files in place

    dsdir = docset_name + ".docset"
    contdir = os.path.join(dsdir, "Contents")
    htmldir = os.path.join(contdir, "Resources", "Documents")

    if os.path.isdir(dsdir):
        print("Warning: Deleting existing docset.")
        shutil.rmtree(dsdir)

    os.makedirs(htmldir)
    for file in glob(os.path.join(docdir, "*.*")):
        shutil.copy(file, htmldir)

    shutil.copy("Info.plist", os.path.join(contdir, "Info.plist"))
    shutil.copy("icon.png", os.path.join(dsdir, "icon.png"))

    # Set up SQLite index

    conn = sqlite3.connect(os.path.join(contdir, "Resources", "docSet.dsidx"))
    cur = conn.cursor()

    cur.execute(
        "CREATE TABLE searchIndex(id INTEGER PRIMARY KEY, name TEXT, type TEXT, path TEXT);"
    )
    cur.execute("CREATE UNIQUE INDEX anchor ON searchIndex (name, type, path);")

    # Parse the index page from the igraph docs to find symbols
    # Results will be stored into the docsysm dictionary

    page = open(os.path.join(htmldir, "ix01.html")).read()

    soup = BeautifulSoup(page, features="lxml")

    docsyms = {}
    for tag in soup.find_all("dt"):
        ch = list(tag.children)
        name = ch[1].text.split()[0]
        link = ch[1].attrs["href"].strip()

        # This is a first guess about the symbol type; it will be refined later
        if name.endswith("_t"):
            kind = "Type"
        elif "_rngtype_" in name:
            kind = "Type"
        else:
            kind = "Function"

        docsyms[name] = (name, kind, link)

    # Update HTML files with information on which symbols they document
    # Also refine symbol type guesses

    for file in glob(os.path.join(htmldir, "igraph-*.html")):
        tree = parse(file)
        anchors = tree.findall("//a[@name]")
        for a in anchors:
            name = a.attrib["name"]
            if name in docsyms:
                (_, kind, link) = docsyms[name]

                # Parse the declaration of the symbol, if present, and refine the guess about its type.
                pre = a.find("../../../../..//pre")
                if pre is not None:
                    code = pre.text_content().strip()
                    if code.startswith("typedef enum"):
                        kind = "Enum"
                    elif code.startswith("typedef struct"):
                        kind = "Struct"
                    elif code.startswith("typedef"):
                        kind = "Type"
                    elif code.startswith("#define"):
                        kind = "Define"
                docsyms[name] = (name, kind, link)
                p = a.getparent()
                p.insert(
                    p.index(a) + 1,
                    fromstring(
                        "<a name='//apple_ref/cpp/%s/%s' class='dashAnchor' />"
                        % (kind, name)
                    ),
                )

        with open(file, "bw") as htmlfile:
            htmlfile.write(tostring(tree))

    # Insert symbols into index

    for triplet in docsyms.values():
        cur.execute(
            "INSERT OR IGNORE INTO searchIndex(name, type, path) VALUES (?,?,?)",
            triplet,
        )
        # print('name: %s, kind: %s, link: %s' % triplet)

    conn.commit()
    conn.close()


def create_dash_submission(version, revision=0):
    """
    Prepares a submission for https://github.com/Kapeli/Dash-User-Contributions.
    The docset must be present in the current directory.
    """

    from string import Template

    print("Creating Dash submission ...")

    subdir = "submission"

    if os.path.isdir(subdir):
        print("Warning: Deleting existing submission directory.")
        shutil.rmtree(subdir)

    os.mkdir(subdir)

    tem = Template(open("docset.json", "r").read())
    open(os.path.join(subdir, "docset.json"), "w").write(
        tem.substitute(version=version, revision=revision)
    )

    with tarfile.open("igraph.tgz", "w:gz") as tar:
        tar.add("igraph.docset")

    shutil.move("igraph.tgz", subdir)

    shutil.copy("README.md", subdir)
    shutil.copy("icon.png", subdir)


if __name__ == "__main__":

    os.chdir(os.path.dirname(os.path.realpath(__file__)))

    version = download_release()
    create_docset("html")
    shutil.rmtree("html")
    create_dash_submission(version)

    print("Done!")
