using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using Pivoki.Core;

namespace Pivoki.Windows;

internal sealed class PackageEditorWindow : Window
{
    private readonly OutputPackage? original;
    private readonly TextBox packageName = new();
    private readonly StackPanel outputRows = new();
    private readonly List<(ComboBox Format, TextBox Edge, TextBox Folder, Grid Row)> fields = [];
    private readonly StackPanel body = new() { Margin = new Thickness(24) };
    internal OutputPackage? Saved { get; private set; }

    internal PackageEditorWindow(Window owner, OutputPackage? original)
    {
        this.original = original;
        Owner = owner;
        Theme.Attach(this);
        Title = L10n.Text(original is null ? "Create package" : "Edit package");
        Width = 660;
        Height = 540;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        Content = new ScrollViewer { Content = body, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
        body.Children.Add(Label("Package name", packageName));
        packageName.Text = original?.Name ?? "";
        body.Children.Add(packageName);
        body.Children.Add(outputRows);
        foreach (var output in original?.Outputs ?? [new("webp",1600,"web"), new("jpg",400,"small")]) AddRow(output);
        var buttons = new WrapPanel();
        buttons.Children.Add(MainWindow.Button("Add output", () => AddRow(new("png",800,""))));
        buttons.Children.Add(MainWindow.Primary("Save package", async () => await SaveAsync()));
        var cancel = MainWindow.Button("Cancel", () => Close());
        cancel.IsCancel = true;
        buttons.Children.Add(cancel);
        body.Children.Add(buttons);
        Loaded += (_,_) => packageName.Focus();
    }

    internal static Label Label(string text, Control field)
    {
        AutomationProperties.SetName(field,L10n.Text(text));
        return new Label { Content=L10n.Text(text), Target=field, Foreground=Theme.Brush("Ink") };
    }

    private void AddRow(PackageOutput output)
    {
        var row = new Grid();
        foreach (var width in new[]{1.1, 1.1, 1.6, 1.1})
            row.ColumnDefinitions.Add(new() { Width = new GridLength(width,GridUnitType.Star) });
        var format = new ComboBox { ItemsSource=new[]{"png","jpg","webp"}, SelectedItem=output.Format.ToLowerInvariant() };
        var edge = new TextBox { Text=output.MaxEdge.ToString() };
        var folder = new TextBox { Text=output.RelativeDir };
        var columns = new (Control Field,string Name)[]{ (format,"Format"), (edge,"Longest edge (px)"), (folder,"Relative folder") };
        for (var i=0; i<columns.Length; i++)
        {
            var stack=new StackPanel();
            stack.Children.Add(Label(columns[i].Name,columns[i].Field));
            stack.Children.Add(columns[i].Field);
            Grid.SetColumn(stack,i);
            row.Children.Add(stack);
        }
        var remove=MainWindow.Button("Remove",()=>{
            fields.RemoveAll(field=>field.Row==row);
            outputRows.Children.Remove(row);
        });
        remove.VerticalAlignment=VerticalAlignment.Bottom;
        Grid.SetColumn(remove,3);
        row.Children.Add(remove);
        fields.Add((format,edge,folder,row));
        outputRows.Children.Add(row);
    }

    private async Task SaveAsync()
    {
        try
        {
            var name=packageName.Text.Trim();
            if(name.Length==0 || fields.Count==0) throw new ArgumentException(L10n.Text("Enter a package name and at least one output."));
            var outputs=new List<PackageOutput>();
            foreach(var field in fields)
            {
                if(!int.TryParse(field.Edge.Text,out var edge) || edge<1)
                    throw new ArgumentException(L10n.Text("The longest edge must be a positive number."));
                outputs.Add(new((string)field.Format.SelectedItem,edge,field.Folder.Text.Trim()));
            }
            body.IsEnabled=false;
            var reply=await PackageEngine.RequestAsync(new {action="savePackage",package=new { packageId=original?.PackageId,revision=original?.Revision,name,outputs }});
            Saved=reply.Package ?? throw new InvalidDataException("The engine did not return the saved package.");
            DialogResult=true;
        }
        catch(Exception error){MessageBox.Show(this,error.Message,Title);}
        finally{body.IsEnabled=true;}
    }
}
