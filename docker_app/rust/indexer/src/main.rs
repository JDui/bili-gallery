use anyhow::{bail, Context, Result};
use serde::Serialize;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Serialize)]
struct ScanResult {
    ok: bool,
    folders: Vec<FolderScan>,
    missing: Vec<String>,
    orphan_files: Vec<FileEntry>,
}

#[derive(Serialize)]
struct FolderScan {
    folder_name: String,
    images: Vec<FileEntry>,
    livephotos: Vec<FileEntry>,
}

#[derive(Serialize, Clone)]
struct FileEntry {
    folder_name: String,
    filename: String,
    rel_path: String,
    bytes: u64,
}

fn main() {
    if let Err(error) = run() {
        println!(
            "{}",
            serde_json::json!({
                "ok": false,
                "error": error.to_string(),
            })
        );
        std::process::exit(1);
    }
}

fn run() -> Result<()> {
    let args: Vec<String> = env::args().collect();
    match args.get(1).map(String::as_str) {
        Some("scan") => {
            let images_dir = arg_path(&args, "--images-dir")?;
            let livephoto_dir = arg_path(&args, "--livephoto-dir")?;
            let result = scan(&images_dir, &livephoto_dir)?;
            println!("{}", serde_json::to_string(&result)?);
            Ok(())
        }
        _ => bail!("usage: indexer scan --images-dir PATH --livephoto-dir PATH"),
    }
}

fn scan(images_dir: &Path, livephoto_dir: &Path) -> Result<ScanResult> {
    let mut folder_names = names_in(images_dir)?;
    for name in names_in(livephoto_dir)? {
        if !folder_names.contains(&name) {
            folder_names.push(name);
        }
    }
    folder_names.sort();
    let mut folders = Vec::new();
    let mut missing = Vec::new();
    for folder_name in folder_names {
        let image_folder = images_dir.join(&folder_name);
        let live_folder = livephoto_dir.join(&folder_name);
        let images = list_media(&image_folder, &folder_name, &["jpg", "jpeg", "png", "webp", "bmp"])?;
        let livephotos = list_media(&live_folder, &folder_name, &["mp4", "mov", "m4v", "webm"])?;
        if images.is_empty() && !image_folder.exists() {
            missing.push(format!("images/{folder_name}"));
        }
        if livephotos.is_empty() && !live_folder.exists() {
            missing.push(format!("livephoto/{folder_name}"));
        }
        folders.push(FolderScan {
            folder_name,
            images,
            livephotos,
        });
    }
    Ok(ScanResult {
        ok: true,
        folders,
        missing,
        orphan_files: Vec::new(),
    })
}

fn names_in(root: &Path) -> Result<Vec<String>> {
    if !root.exists() {
        return Ok(Vec::new());
    }
    let mut names = Vec::new();
    for entry in fs::read_dir(root).with_context(|| format!("read dir {}", root.display()))? {
        let entry = entry?;
        if entry.file_type()?.is_dir() {
            names.push(entry.file_name().to_string_lossy().to_string());
        }
    }
    Ok(names)
}

fn list_media(root: &Path, folder_name: &str, extensions: &[&str]) -> Result<Vec<FileEntry>> {
    if !root.exists() {
        return Ok(Vec::new());
    }
    let mut output = Vec::new();
    for entry in fs::read_dir(root).with_context(|| format!("read dir {}", root.display()))? {
        let entry = entry?;
        if !entry.file_type()?.is_file() {
            continue;
        }
        let path = entry.path();
        let filename = entry.file_name().to_string_lossy().to_string();
        if filename.starts_with('.') {
            continue;
        }
        let ext = path.extension().and_then(|value| value.to_str()).unwrap_or("").to_ascii_lowercase();
        if !extensions.iter().any(|item| *item == ext) {
            continue;
        }
        output.push(FileEntry {
            folder_name: folder_name.to_string(),
            filename: filename.clone(),
            rel_path: path.display().to_string(),
            bytes: entry.metadata()?.len(),
        });
    }
    output.sort_by(|left, right| left.filename.cmp(&right.filename));
    Ok(output)
}

fn arg_path(args: &[String], name: &str) -> Result<PathBuf> {
    args.windows(2)
        .find(|pair| pair[0] == name)
        .map(|pair| PathBuf::from(&pair[1]))
        .with_context(|| format!("missing argument {name}"))
}
