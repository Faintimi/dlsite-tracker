// 同人游戏雷达 · Doujin Game Radar —— 桌面端后端命令
// 职责：数据文件选择 / 记住最近使用的 works.json / 为封面图片登记资产协议读取范围。
// 数据只在本机流转：所有命令都只读本地文件，不做任何网络访问。

use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Manager};
use tauri_plugin_dialog::DialogExt;

#[derive(Debug, Default, Clone, Serialize, Deserialize)]
#[serde(default)]
struct Settings {
    /// 最近一次选择的 works.json 绝对路径
    data_path: Option<String>,
}

fn settings_file(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = app.path().app_config_dir().map_err(|e| e.to_string())?;
    fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    Ok(dir.join("settings.json"))
}

fn read_settings(app: &AppHandle) -> Settings {
    settings_file(app)
        .ok()
        .and_then(|path| fs::read_to_string(path).ok())
        .and_then(|raw| serde_json::from_str(&raw).ok())
        .unwrap_or_default()
}

fn write_settings(app: &AppHandle, settings: &Settings) -> Result<(), String> {
    let path = settings_file(app)?;
    let raw = serde_json::to_string_pretty(settings).map_err(|e| e.to_string())?;
    fs::write(path, raw).map_err(|e| e.to_string())
}

/// 为 works.json 所在目录登记资产协议读取范围（封面在 <目录>/covers 下）。
/// 仅登记运行时范围：重启后由 `setup` 依据持久化设置重新登记。
fn allow_data_dir(app: &AppHandle, data_path: &Path) -> Result<(), String> {
    if let Some(dir) = data_path.parent() {
        app.asset_protocol_scope()
            .allow_directory(dir, true)
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

/// 返回最近使用的数据文件路径（未设置则为 null）。
#[tauri::command]
fn get_data_path(app: AppHandle) -> Option<String> {
    read_settings(&app).data_path
}

/// 打开文件选择框；选中后持久化并登记读取范围。
#[tauri::command]
async fn pick_data_file(app: AppHandle) -> Result<Option<String>, String> {
    let current = read_settings(&app).data_path;
    let mut dialog = app
        .dialog()
        .file()
        .set_title("选择游戏数据文件")
        .add_filter("works.json", &["json"]);
    if let Some(dir) = current.as_deref().and_then(|p| Path::new(p).parent()) {
        dialog = dialog.set_directory(dir);
    }
    let Some(picked) = dialog.blocking_pick_file() else {
        return Ok(None);
    };
    let path = picked.into_path().map_err(|e| e.to_string())?;
    allow_data_dir(&app, &path)?;
    write_settings(
        &app,
        &Settings { data_path: Some(path.to_string_lossy().into_owned()) },
    )?;
    Ok(Some(path.to_string_lossy().into_owned()))
}

/// 读取 works.json 原文；解析（JSON.parse）放在前端完成。
#[tauri::command]
fn load_works(app: AppHandle) -> Result<String, String> {
    let path = read_settings(&app).data_path.ok_or("尚未选择数据文件")?;
    match fs::read_to_string(&path) {
        Ok(raw) => {
            println!("[radar] 已读取数据文件：{path}（{} 字节）", raw.len());
            Ok(raw)
        }
        Err(e) => {
            let message = format!("读取 {path} 失败：{e}");
            eprintln!("[radar] {message}");
            Err(message)
        }
    }
}

/// 收藏 / 关注数据文件（应用配置目录下 favorites.json；与 macOS 版同构便于迁移）。
fn library_file(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = app.path().app_config_dir().map_err(|e| e.to_string())?;
    fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    Ok(dir.join("favorites.json"))
}

/// 读取收藏数据原文（不存在返回 null，由前端建默认结构）。
#[tauri::command]
fn load_library(app: AppHandle) -> Result<Option<String>, String> {
    let path = library_file(&app)?;
    match fs::read_to_string(&path) {
        Ok(raw) => Ok(Some(raw)),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(e) => Err(format!("读取 {} 失败：{e}", path.display())),
    }
}

/// 原子保存收藏数据（先写临时文件再改名，失败不破坏旧档）。
#[tauri::command]
fn save_library(app: AppHandle, data: String) -> Result<(), String> {
    let path = library_file(&app)?;
    let tmp = path.with_extension("json.tmp");
    fs::write(&tmp, data).map_err(|e| e.to_string())?;
    fs::rename(&tmp, &path).map_err(|e| e.to_string())
}

/// 数据目录（works.json 所在目录，进度文件也在这里）。
fn out_dir_of(app: &AppHandle) -> Result<PathBuf, String> {
    let data_path = read_settings(app).data_path.ok_or("尚未选择数据文件")?;
    PathBuf::from(data_path)
        .parent()
        .map(|path| path.to_path_buf())
        .ok_or_else(|| "数据文件路径无效".to_string())
}

/// 进度文件原文（不存在返回 null）：update / import / genre 进度 + 已覆盖最深位置。
#[derive(serde::Serialize)]
struct ProgressFiles {
    update: Option<String>,
    import_progress: Option<String>,
    genre: Option<String>,
    import_coverage: Option<String>,
}

#[tauri::command]
fn read_progress_files(app: AppHandle) -> Result<ProgressFiles, String> {
    let out_dir = out_dir_of(&app)?;
    Ok(ProgressFiles {
        update: fs::read_to_string(out_dir.join("update-progress.json")).ok(),
        import_progress: fs::read_to_string(out_dir.join("import-progress.json")).ok(),
        genre: fs::read_to_string(out_dir.join("genre-progress.json")).ok(),
        import_coverage: fs::read_to_string(out_dir.join("import-coverage.json")).ok(),
    })
}

/// 项目目录（out 的上一级）。
fn project_dir_of(app: &AppHandle) -> Result<PathBuf, String> {
    let out_dir = out_dir_of(app)?;
    out_dir
        .parent()
        .map(|path| path.to_path_buf())
        .ok_or_else(|| "无法确定项目目录（out 的上一级）".to_string())
}

/// 后台启动一个管道子进程（stdout/stderr 丢弃，线程回收退出码）。
fn spawn_pipeline(project_dir: &Path, program: &str, args: &[&str]) -> Result<(), String> {
    let mut command = Command::new(program);
    command
        .args(args)
        .current_dir(project_dir)
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    let child = command.spawn().map_err(|e| format!("无法启动任务：{e}"))?;
    std::thread::spawn(move || {
        let mut child = child;
        let _ = child.wait();
    });
    Ok(())
}

/// 渐进导入开关（对应 macOS 版 scripts/import.sh start|pause）。
/// on=true 时按范围启动/续传；on=false 时优雅暂停（断点保留）。
#[tauri::command]
fn import_switch(app: AppHandle, on: bool, years: Option<String>) -> Result<String, String> {
    let project_dir = project_dir_of(&app)?;
    let years = years.unwrap_or_else(|| "1".to_string());
    #[cfg(windows)]
    {
        if on {
            spawn_pipeline(
                &project_dir,
                "python",
                &["-m", "dlsite_tracker", "import-recent", "--years", &years],
            )?;
            Ok(format!("已开启渐进导入（{years}）"))
        } else {
            spawn_pipeline(
                &project_dir,
                "python",
                &["-m", "dlsite_tracker", "import-recent", "--pause"],
            )?;
            Ok("已暂停渐进导入".to_string())
        }
    }
    #[cfg(not(windows))]
    {
        let script = project_dir.join("scripts").join("import.sh");
        if !script.is_file() {
            return Err(format!("未找到导入脚本：{}", script.display()));
        }
        let script = script.to_string_lossy().into_owned();
        if on {
            spawn_pipeline(&project_dir, "/bin/bash", &[&script, "start", &years])?;
            Ok(format!("已开启渐进导入（{years}）"))
        } else {
            // pause 会等待信号送达（脚本内 exec 同一进程），因此同步等待
            let status = Command::new("/bin/bash")
                .args([&script, "pause"])
                .current_dir(&project_dir)
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status();
            match status {
                Ok(_) => Ok("已暂停渐进导入".to_string()),
                Err(e) => Err(format!("暂停导入失败：{e}")),
            }
        }
    }
}

/// 取消渐进导入任务（已入库作品保留）。
#[tauri::command]
fn cancel_import(app: AppHandle) -> Result<String, String> {
    let project_dir = project_dir_of(&app)?;
    #[cfg(windows)]
    {
        spawn_pipeline(
            &project_dir,
            "python",
            &["-m", "dlsite_tracker", "import-recent", "--cancel"],
        )?;
        Ok("已取消导入任务".to_string())
    }
    #[cfg(not(windows))]
    {
        let script = project_dir.join("scripts").join("import.sh");
        if !script.is_file() {
            return Err(format!("未找到导入脚本：{}", script.display()));
        }
        let status = Command::new("/bin/bash")
            .arg(script)
            .arg("cancel")
            .current_dir(&project_dir)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
        match status {
            Ok(_) => Ok("已取消导入任务".to_string()),
            Err(e) => Err(format!("取消导入失败：{e}")),
        }
    }
}

/// 分类人气：现导入（前 N 页）/ 载入更多（--more，续抓一页）。
#[tauri::command]
fn start_genre_import(app: AppHandle, genre: String, more: bool) -> Result<String, String> {
    let project_dir = project_dir_of(&app)?;
    #[cfg(windows)]
    {
        let mut args: Vec<&str> = vec!["-m", "dlsite_tracker", "fetch-genre", &genre];
        if more {
            args.push("--more");
        }
        spawn_pipeline(&project_dir, "python", &args)?;
        Ok(format!("已启动分类 {genre} 抓取"))
    }
    #[cfg(not(windows))]
    {
        let script = project_dir.join("scripts").join("genre-import.sh");
        if !script.is_file() {
            return Err(format!("未找到分类抓取脚本：{}", script.display()));
        }
        let script = script.to_string_lossy().into_owned();
        if more {
            spawn_pipeline(&project_dir, "/bin/bash", &[&script, &genre, "--more"])?;
        } else {
            spawn_pipeline(&project_dir, "/bin/bash", &[&script, &genre])?;
        }
        Ok(format!("已启动分类 {genre} 抓取"))
    }
}

/// 把分类加入每日刷新列表（写入配置 genre_rank_ids）。
#[tauri::command]
fn watch_genre(app: AppHandle, genre: String) -> Result<String, String> {
    let project_dir = project_dir_of(&app)?;
    #[cfg(windows)]
    {
        spawn_pipeline(
            &project_dir,
            "python",
            &["-m", "dlsite_tracker", "watch-genre", &genre],
        )?;
        Ok(format!("已加入每日刷新：{genre}"))
    }
    #[cfg(not(windows))]
    {
        let script = project_dir.join("scripts").join("genre-import.sh");
        if !script.is_file() {
            return Err(format!("未找到分类抓取脚本：{}", script.display()));
        }
        let status = Command::new("/bin/bash")
            .arg(script)
            .arg("watch")
            .arg(&genre)
            .current_dir(&project_dir)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
        match status {
            Ok(_) => Ok(format!("已加入每日刷新：{genre}")),
            Err(e) => Err(format!("加入每日刷新失败：{e}")),
        }
    }
}

/// 启动管道任务（quick / daily / update-all[range]）。
/// 进程独立运行，进度与结果通过进度文件 / 日志反馈，应用不做等待。
#[tauri::command]
fn start_update(app: AppHandle, kind: String, range: Option<String>) -> Result<String, String> {
    let project_dir = project_dir_of(&app)?;

    #[cfg(windows)]
    {
        let chain = match kind.as_str() {
            "quick" => "quick",
            "daily" => "daily",
            "update-all" => "update-all",
            _ => return Err(format!("未知任务类型：{kind}")),
        };
        let mut command = Command::new("python");
        command.arg("-m").arg("dlsite_tracker").arg("task").arg(chain);
        if let Some(value) = range.as_deref().filter(|value| !value.is_empty()) {
            command.arg(value);
        }
        command
            .current_dir(project_dir)
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        let child = command.spawn().map_err(|e| format!("无法启动更新：{e}"))?;
        std::thread::spawn(move || {
            let mut child = child;
            let _ = child.wait();
        });
        Ok(format!("已启动 {chain}"))
    }

    #[cfg(not(windows))]
    {
        let script = match kind.as_str() {
            "quick" => "quick-update.sh",
            "daily" => "daily.sh",
            "update-all" => "update-all.sh",
            _ => return Err(format!("未知任务类型：{kind}")),
        };
        let script_path = project_dir.join("scripts").join(script);
        if !script_path.is_file() {
            return Err(format!("未找到更新脚本：{}", script_path.display()));
        }
        let mut command = Command::new("/bin/bash");
        command.arg(&script_path);
        if kind == "update-all" {
            command.arg(range.as_deref().unwrap_or("1"));
        }
        command
            .current_dir(project_dir)
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        let child = command.spawn().map_err(|e| format!("无法启动更新：{e}"))?;
        std::thread::spawn(move || {
            let mut child = child;
            let _ = child.wait();
        });
        Ok(format!("已启动 {script}"))
    }
}

/// 本地同步导出（对齐 macOS 版「更新」：先跑管道导出，再重读文件）。
/// 返回 "ok"（已导出）或 "no-export"（非管道目录布局，调用方直接重读即可）。
#[tauri::command]
async fn run_export(app: AppHandle) -> Result<String, String> {
    let project_dir = project_dir_of(&app)?;
    #[cfg(windows)]
    {
        let status = Command::new("python")
            .args(["-m", "dlsite_tracker", "export"])
            .current_dir(&project_dir)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
        match status {
            Ok(code) if code.success() => Ok("ok".to_string()),
            Ok(_) => Err("导出失败：详见 data/ 目录日志".to_string()),
            Err(_) => Ok("no-export".to_string()),
        }
    }
    #[cfg(not(windows))]
    {
        let script = project_dir.join("scripts").join("export.sh");
        if !script.is_file() {
            return Ok("no-export".to_string());
        }
        let status = Command::new("/bin/bash")
            .arg(&script)
            .current_dir(&project_dir)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
        match status {
            Ok(code) if code.success() => Ok("ok".to_string()),
            Ok(_) => Err("导出失败：详见 data/ 目录日志".to_string()),
            Err(e) => Err(format!("导出失败：{e}")),
        }
    }
}

/// macOS 版收藏数据（~/Library/Application Support/DoujinGameFinder/favorites.json）。
#[derive(serde::Serialize)]
struct MacosFavorites {
    path: String,
    raw: String,
}

/// 读取 macOS 原生版的收藏文件原文（不存在返回 null；供一次性迁移）。
#[tauri::command]
fn read_macos_favorites(app: AppHandle) -> Result<Option<MacosFavorites>, String> {
    let home = app.path().home_dir().map_err(|e| e.to_string())?;
    let path = home
        .join("Library")
        .join("Application Support")
        .join("DoujinGameFinder")
        .join("favorites.json");
    match fs::read_to_string(&path) {
        Ok(raw) => Ok(Some(MacosFavorites {
            path: path.to_string_lossy().into_owned(),
            raw,
        })),
        Err(_) => Ok(None),
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            match read_settings(app.handle()).data_path {
                Some(path) => match allow_data_dir(app.handle(), Path::new(&path)) {
                    Ok(()) => println!("[radar] 数据文件：{path}（已登记封面读取范围）"),
                    Err(e) => eprintln!("[radar] 封面读取范围登记失败：{e}"),
                },
                None => println!("[radar] 尚未选择数据文件"),
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_data_path,
            pick_data_file,
            load_works,
            load_library,
            save_library,
            read_progress_files,
            start_update,
            import_switch,
            cancel_import,
            start_genre_import,
            watch_genre,
            run_export,
            read_macos_favorites
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
